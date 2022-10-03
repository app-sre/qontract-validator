#!/usr/bin/env python2

import hashlib
import os
import re
import sys
import logging

import click
import json

from multiprocessing.dummy import Pool as ThreadPool
from validator.bundle import Bundle

from validator.utils import parse_anymarkup_file
from validator.postprocess import postprocess_bundle

logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.WARNING)

# regex to get the schema from the resource files.
# we use multiline as we have a raw string with newlines caracters
# we don't use pyyaml to parse it as they are jinja templates in most cases
SCHEMA_RE = re.compile(r'^\$schema: (?P<schema>.+\.ya?ml)$', re.MULTILINE)


def bundle_datafiles(data_dir, thread_pool_size):
    specs = init_specs(data_dir)
    pool = ThreadPool(thread_pool_size)
    results = pool.map(bundle_datafile_spec, specs)
    results = [r for r in results if r is not None]
    return {k: v for k, v in results}


def bundle_datafile_spec(spec):
    work_dir = spec['work_dir']
    root = spec['root']
    name = spec['name']
    if not re.search(r'\.(ya?ml|json)$', name):
        return None

    path = os.path.join(root, name)
    rel_abs_path = path[len(work_dir):]

    logging.info("Processing: {}\n".format(rel_abs_path))

    return rel_abs_path, parse_anymarkup_file(path)


def bundle_resources(resource_dir, thread_pool_size):
    specs = init_specs(resource_dir)
    pool = ThreadPool(thread_pool_size)
    results = pool.map(bundle_resource_spec, specs)
    return {k: v for k, v in results}


def bundle_resource_spec(spec):
    work_dir = spec['work_dir']
    root = spec['root']
    name = spec['name']
    path = os.path.join(root, name)
    rel_abs_path = path[len(work_dir):]
    logging.info("Resource: {}\n".format(rel_abs_path))

    with open(path, 'rb') as f:
        content = f.read().decode(errors='replace')

    schema = None
    s = SCHEMA_RE.search(content)
    if s:
        schema = s.group('schema')

    # hash
    m = hashlib.sha256()
    m.update(content.encode())
    sha256sum = m.hexdigest()

    return rel_abs_path, {"path": rel_abs_path,
                          "content": content,
                          "$schema": schema,
                          "sha256sum": sha256sum,
                          "backrefs": []}


def init_specs(work_dir):
    specs = []
    for root, dirs, files in os.walk(work_dir, topdown=False):
        for name in files:
            spec = {
                "work_dir": work_dir,
                "root": root,
                "name": name,
            }
            specs.append(spec)
    return specs


def bundle_graphql(graphql_schema_file):
    return parse_anymarkup_file(graphql_schema_file)


def fix_dir(directory):
    if directory[-1] == "/":
        directory = directory[:-1]
    return directory


@click.command()
@click.option('--resolve', is_flag=True, help='Resolve references')
@click.option('--thread-pool-size', default=10,
              help='number of threads to run in parallel.')
@click.argument('schema-dir', type=click.Path(exists=True))
@click.argument('graphql-schema-file', type=click.Path(exists=True))
@click.argument('data-dir', type=click.Path(exists=True))
@click.argument('resource-dir', type=click.Path(exists=True))
@click.argument('git-commit')
@click.argument('git-commit-timestamp')
def main(resolve, thread_pool_size,
         schema_dir, graphql_schema_file, data_dir, resource_dir,
         git_commit, git_commit_timestamp):
    schema_dir = fix_dir(schema_dir)
    data_dir = fix_dir(data_dir)
    resource_dir = fix_dir(resource_dir)

    bundle = Bundle(
        git_commit=git_commit,
        git_commit_timestamp=git_commit_timestamp,
        schemas=bundle_datafiles(schema_dir, thread_pool_size),
        graphql=bundle_graphql(graphql_schema_file),
        data=bundle_datafiles(data_dir, thread_pool_size),
        resources=bundle_resources(resource_dir, thread_pool_size)
    )

    postprocess_bundle(bundle)

    sys.stdout.write(json.dumps(bundle.to_dict()) + "\n")
