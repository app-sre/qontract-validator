#!/usr/bin/env python2

import hashlib
import json
import logging
import os
import re
import sys
from multiprocessing.dummy import Pool as ThreadPool

import click

from validator.bundle import Bundle
from validator.postprocess import postprocess_bundle
from validator.utils import parse_anymarkup_file

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.WARNING)

# regex to get the schema from the resource files.
# we use multiline as we have a raw string with newlines caracters
# we don't use pyyaml to parse it as they are jinja templates in most cases
SCHEMA_RE = re.compile(r"^\$schema: (?P<schema>.+\.ya?ml)$", re.MULTILINE)

CHECKSUM_SCHEMA_FIELD = "$file_sha256sum"


def bundle_datafiles(data_dir, thread_pool_size, checksum_field_name=None):
    specs = init_specs(data_dir, checksum_field_name is not None)
    pool = ThreadPool(thread_pool_size)
    results = pool.map(bundle_datafile_spec, specs)

    def do_inject_checksum(content, checksum):
        if checksum_field_name:
            content[checksum_field_name] = checksum
        return content

    return {
        path: do_inject_checksum(content, sha256sum)
        for path, content, sha256sum in results
        if path is not None
    }


def bundle_datafile_spec(spec):
    work_dir = spec["work_dir"]
    root = spec["root"]
    name = spec["name"]
    if not re.search(r"\.(ya?ml|json)$", name):
        return None, None, None

    path = os.path.join(root, name)
    rel_abs_path = path[len(work_dir) :]

    logging.info(f"Processing: {rel_abs_path}\n")
    content, checksum = parse_anymarkup_file(path, spec["calc_checksum"])
    return rel_abs_path, content, checksum


def bundle_resources(resource_dir, thread_pool_size):
    specs = init_specs(resource_dir)
    pool = ThreadPool(thread_pool_size)
    results = pool.map(bundle_resource_spec, specs)
    return dict(results)


def bundle_resource_spec(spec):
    work_dir = spec["work_dir"]
    root = spec["root"]
    name = spec["name"]
    path = os.path.join(root, name)
    rel_abs_path = path[len(work_dir) :]
    logging.info(f"Resource: {rel_abs_path}\n")

    with open(path, "rb") as f:
        content = f.read().decode(errors="replace")

    schema = None
    s = SCHEMA_RE.search(content)
    if s:
        schema = s.group("schema")

    # hash
    m = hashlib.sha256()
    m.update(content.encode())
    sha256sum = m.hexdigest()

    return rel_abs_path, {
        "path": rel_abs_path,
        "content": content,
        "$schema": schema,
        "sha256sum": sha256sum,
        "backrefs": [],
    }


def init_specs(work_dir, calc_checksum=False):
    specs = []
    for root, _, files in os.walk(work_dir, topdown=False):
        for name in files:
            spec = {
                "work_dir": work_dir,
                "root": root,
                "name": name,
                "calc_checksum": calc_checksum,
            }
            specs.append(spec)
    return specs


def bundle_graphql(graphql_schema_file):
    content, _ = parse_anymarkup_file(graphql_schema_file)
    return content


def fix_dir(directory):
    if directory[-1] == "/":
        directory = directory[:-1]
    return directory


@click.command()
@click.option("--resolve", is_flag=True, help="Resolve references")
@click.option(
    "--thread-pool-size", default=10, help="number of threads to run in parallel."
)
@click.argument("schema-dir", type=click.Path(exists=True))
@click.argument("graphql-schema-file", type=click.Path(exists=True))
@click.argument("data-dir", type=click.Path(exists=True))
@click.argument("resource-dir", type=click.Path(exists=True))
@click.argument("git-commit")
@click.argument("git-commit-timestamp")
def main(
    resolve,
    thread_pool_size,
    schema_dir,
    graphql_schema_file,
    data_dir,
    resource_dir,
    git_commit,
    git_commit_timestamp,
):
    schema_dir = fix_dir(schema_dir)
    data_dir = fix_dir(data_dir)
    resource_dir = fix_dir(resource_dir)

    bundle = Bundle(
        git_commit=git_commit,
        git_commit_timestamp=git_commit_timestamp,
        schemas=bundle_datafiles(schema_dir, thread_pool_size),
        graphql=bundle_graphql(graphql_schema_file),
        data=bundle_datafiles(
            data_dir, thread_pool_size, checksum_field_name=CHECKSUM_SCHEMA_FIELD
        ),
        resources=bundle_resources(resource_dir, thread_pool_size),
    )

    postprocess_bundle(bundle, checksum_field_name=CHECKSUM_SCHEMA_FIELD)

    sys.stdout.write(json.dumps(bundle.to_dict()) + "\n")
