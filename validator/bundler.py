#!/usr/bin/env python2

import hashlib
import os
import re
import sys

import anymarkup
import click
import json


def bundle_datafiles(data_dir):
    bundle = {}
    for root, dirs, files in os.walk(data_dir, topdown=False):
        for name in files:
            if re.search(r'\.(ya?ml|json)$', name):
                path = os.path.join(root, name)
                rel_abs_path = path[len(data_dir):]

                sys.stderr.write("Processing: {}\n".format(rel_abs_path))

                bundle[rel_abs_path] = anymarkup.parse_file(
                    path, force_types=None)
    return bundle


def bundle_resources(resource_dir):
    bundle = {}

    for root, dirs, files in os.walk(resource_dir, topdown=False):
        for name in files:
            path = os.path.join(root, name)
            rel_abs_path = path[len(resource_dir):]
            sys.stderr.write("Resource: {}\n".format(rel_abs_path))

            content = open(path, 'r').read()

            # hash
            m = hashlib.sha256()
            m.update(content)
            sha256sum = m.hexdigest()

            bundle[rel_abs_path] = {
                "path": rel_abs_path,
                "content": content,
                "sha256sum": sha256sum
            }

    return bundle


def bundle_graphql(graphql_schema_file):
    return anymarkup.parse_file(graphql_schema_file, force_types=None)


def fix_dir(directory):
    if directory[-1] == "/":
        directory = directory[:-1]
    return directory


@click.command()
@click.option('--resolve', is_flag=True, help='Resolve references')
@click.argument('schema-dir', type=click.Path(exists=True))
@click.argument('graphql-schema-file', type=click.Path(exists=True))
@click.argument('data-dir', type=click.Path(exists=True))
@click.argument('resource-dir', type=click.Path(exists=True))
def main(resolve, schema_dir, graphql_schema_file, data_dir, resource_dir):
    schema_dir = fix_dir(schema_dir)
    data_dir = fix_dir(data_dir)
    resource_dir = fix_dir(resource_dir)

    bundle = {}

    bundle['schemas'] = bundle_datafiles(schema_dir)
    bundle['graphql'] = bundle_graphql(graphql_schema_file)
    bundle['data'] = bundle_datafiles(data_dir)
    bundle['resources'] = bundle_resources(resource_dir)

    sys.stdout.write(json.dumps(bundle, indent=4) + "\n")
