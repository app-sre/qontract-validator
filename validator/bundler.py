#!/usr/bin/env python2

import os
import re
import sys

import anymarkup
import click
import json


@click.command()
@click.option('--resolve', is_flag=True, help='Resolve references')
@click.argument('data-dir')
def main(resolve, data_dir):
    if data_dir[-1] == "/":
        data_dir = data_dir[:-1]

    bundle = {}

    for root, dirs, files in os.walk(data_dir, topdown=False):
        for name in files:
            if re.search(r'\.(ya?ml|json)$', name):
                path = os.path.join(root, name)
                datafile = path[len(data_dir):]

                sys.stderr.write("Processing: {}\n".format(datafile))

                data = anymarkup.parse_file(path, force_types=None)
                bundle[datafile] = data

    sys.stdout.write(json.dumps(bundle, indent=4) + "\n")
