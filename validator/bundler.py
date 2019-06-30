#!/usr/bin/env python2

import hashlib
import os
import re
import sys

import anymarkup
import click
import json

from multiprocessing.dummy import Pool as ThreadPool


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

    sys.stderr.write("Processing: {}\n".format(rel_abs_path))

    return rel_abs_path, anymarkup.parse_file(path, force_types=None)


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
    sys.stderr.write("Resource: {}\n".format(rel_abs_path))

    content = open(path, 'r').read()

    # hash
    m = hashlib.sha256()
    m.update(content)
    sha256sum = m.hexdigest()

    return rel_abs_path, {"path": rel_abs_path,
                          "content": content,
                          "sha256sum": sha256sum}


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
    return anymarkup.parse_file(graphql_schema_file, force_types=None)


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
def main(resolve, thread_pool_size,
         schema_dir, graphql_schema_file, data_dir, resource_dir):
    schema_dir = fix_dir(schema_dir)
    data_dir = fix_dir(data_dir)
    resource_dir = fix_dir(resource_dir)

    bundle = {}

    bundle['schemas'] = bundle_datafiles(schema_dir, thread_pool_size)
    bundle['graphql'] = bundle_graphql(graphql_schema_file)
    bundle['data'] = bundle_datafiles(data_dir, thread_pool_size)
    bundle['resources'] = bundle_resources(resource_dir, thread_pool_size)

    sys.stdout.write(json.dumps(bundle, indent=4) + "\n")
