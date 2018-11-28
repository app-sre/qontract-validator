#!/usr/bin/env python

import argparse
import logging
import os
import re
import sys

import anymarkup
import json
import jsonschema
import requests
import cachetools.func

from enum import Enum

logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)


class ValidatedFileKind(Enum):
    SCHEMA = "SCHEMA"
    DATA_FILE = "FILE"


class MissingSchemaFile(Exception):
    def __init__(self, path):
        self.path = path
        message = "file not found: {}".format(path)
        super(Exception, self).__init__(message)


class ValidationResult(object):
    def summary(self):
        status = 'OK' if self.status else 'ERROR'
        return "{}: {} ({})".format(status, self.filename, self.schema_url)


class ValidationOK(ValidationResult):
    status = True

    def __init__(self, kind, filename, schema_url):
        self.kind = kind
        self.filename = filename
        self.schema_url = schema_url

    def dump(self):
        return {
            "filename": self.filename,
            "kind": self.kind.value,
            "result": {
                "summary": self.summary(),
                "status": "OK",
                "schema_url": self.schema_url,
            }
        }


class ValidationError(ValidationResult):
    status = False

    def __init__(self, kind, filename, reason, error, schema_url=None):
        self.kind = kind
        self.filename = filename
        self.reason = reason
        self.error = error
        self.schema_url = schema_url

    def dump(self):
        return {
            "filename": self.filename,
            "kind": self.kind.value,
            "result": {
                "summary": self.summary(),
                "status": "ERROR",
                "schema_url": self.schema_url,
                "reason": self.reason,
                "error": self.error.__str__()
            }
        }

    def error_info(self):
        if self.error.message:
            msg = "{}\n{}".format(self.reason, self.error.message)
        else:
            msg = self.reason

        return msg


def get_resolver(schemas_root, schema):
    schema_path = "file://" + os.path.abspath(schemas_root) + '/'
    return jsonschema.RefResolver(schema_path, schema)


def validate_schema(schemas_root, filename, schema_data):
    kind = ValidatedFileKind.SCHEMA

    logging.info('validating schema: {}'.format(filename))

    try:
        meta_schema_url = schema_data[u'$schema']
    except KeyError as e:
        return ValidationError(kind, filename, "MISSING_SCHEMA_URL", e)

    meta_schema = fetch_schema(schemas_root, meta_schema_url)

    try:
        jsonschema.Draft4Validator.check_schema(schema_data)
        resolver = get_resolver(schemas_root, schema_data)
        validator = jsonschema.Draft4Validator(meta_schema, resolver=resolver)
        validator.validate(schema_data)
    except jsonschema.ValidationError as e:
        return ValidationError(kind, filename, "VALIDATION_ERROR", e,
                               meta_schema_url)
    except (jsonschema.SchemaError, jsonschema.exceptions.RefResolutionError) as e:
        return ValidationError(kind, filename, "SCHEMA_ERROR", e,
                               meta_schema_url)

    return ValidationOK(kind, filename, meta_schema_url)


def validate_file(schemas_root, filename):
    kind = ValidatedFileKind.DATA_FILE

    logging.info('validating file: {}'.format(filename))

    try:
        data = anymarkup.parse_file(filename, force_types=None)
    except anymarkup.AnyMarkupError as e:
        return ValidationError(kind, filename, "FILE_PARSE_ERROR", e)

    try:
        schema_url = data[u'$schema']
    except KeyError as e:
        return ValidationError(kind, filename, "MISSING_SCHEMA_URL", e)

    try:
        schema = fetch_schema(schemas_root, schema_url)
    except MissingSchemaFile as e:
        return ValidationError(kind, filename, "MISSING_SCHEMA_FILE", e,
                               schema_url)
    except requests.HTTPError as e:
        return ValidationError(kind, filename, "HTTP_ERROR", e, schema_url)
    except anymarkup.AnyMarkupError as e:
        return ValidationError(kind, filename, "SCHEMA_PARSE_ERROR", e,
                               schema_url)

    try:
        resolver = get_resolver(schemas_root, schema)
        jsonschema.Draft4Validator(schema, resolver=resolver).validate(data)
    except jsonschema.ValidationError as e:
        return ValidationError(kind, filename, "VALIDATION_ERROR", e,
                               schema_url)
    except jsonschema.SchemaError as e:
        return ValidationError(kind, filename, "SCHEMA_ERROR", e, schema_url)
    except TypeError as e:
        return ValidationError(kind, filename, "SCHEMA_TYPE_ERROR", e,
                               schema_url)

    return ValidationOK(kind, filename, schema_url)


@cachetools.func.lru_cache()
def fetch_schema(schemas_root, schema_url):
    if schema_url.startswith('http'):
        r = requests.get(schema_url)
        r.raise_for_status()
        schema = r.text
    else:
        schema = fetch_schema_file(schemas_root, schema_url)

    return anymarkup.parse(schema, force_types=None)


def fetch_schema_file(schemas_root, schema_url):
    schema_file = os.path.join(schemas_root, schema_url)

    if not os.path.isfile(schema_file):
        raise MissingSchemaFile(schema_file)

    with open(schema_file, 'r') as f:
        schema = f.read()

    return schema


def main():
    # Parser
    parser = argparse.ArgumentParser(
        description='App-Interface Schema Validator')

    parser.add_argument('--schemas-root', required=True,
                        help='Root directory of the schemas')

    parser.add_argument('--data-root', required=True,
                        help='Data directory')

    args = parser.parse_args()

    # Metaschema
    schemas_root = args.schemas_root

    # Find schemas
    schemas = [
        (filename, fetch_schema(schemas_root, os.path.join(dirpath, filename)))
        for dirpath, dirnames, filenames in os.walk(schemas_root)
        for filename in filenames
        if re.search("\.(json|ya?ml)$", filename)
    ]

    # Validate schemas
    results_schemas = [
        validate_schema(schemas_root, filename, schema_data).dump()
        for filename, schema_data in schemas
    ]

    # Validate files
    files = [
        os.path.join(root, filename)
        for root, dirs, files in os.walk(args.data_root)
        for filename in files
    ]

    results_files = [
        validate_file(schemas_root, filename).dump()
        for filename in files
        if re.search("\.(json|ya?ml)$", filename)
        if os.path.isfile(filename)
    ]

    # Calculate errors
    results = results_schemas + results_files

    errors = [
        r
        for r in results
        if r['result']['status'] == 'ERROR'
    ]

    # Output
    print json.dumps(results)

    if len(errors) > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
