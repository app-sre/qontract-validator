import json
import logging
import sys
import re

from enum import Enum

import anymarkup
import click
import jsonschema
import requests

logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)


class ValidatedFileKind(Enum):
    SCHEMA = "SCHEMA"
    DATA_FILE = "FILE"


class MissingSchemaFile(Exception):
    def __init__(self, path):
        self.path = path
        message = "schema not found: {}".format(path)
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


def get_handlers(schemas_bundle):
    """
    Generates a dictionary which will be used as an the `handlers` argument for
    jsonschema.RefResolver.

    `handlers` is a mapping from URI schemes to functions that should be used
    to retrieve them.

    In this case we are overloading the empty string scheme, which will be the
    scheme detected for absolute or relative file paths.
    """
    return {
        '': lambda s: schemas_bundle[s]
    }


def validate_schema(schemas_bundle, filename, schema_data):
    kind = ValidatedFileKind.SCHEMA

    logging.info('validating schema: {}'.format(filename))

    try:
        meta_schema_url = schema_data[u'$schema']
    except KeyError as e:
        return ValidationError(kind, filename, "MISSING_SCHEMA_URL", e)

    if meta_schema_url in schemas_bundle:
        meta_schema = schemas_bundle[meta_schema_url]
    else:
        meta_schema = fetch_schema(meta_schema_url)
        schemas_bundle[meta_schema_url] = meta_schema

    resolver = jsonschema.RefResolver(
        filename,
        schema_data,
        handlers=get_handlers(schemas_bundle)
    )

    jsonschema.Draft4Validator.check_schema(schema_data)
    validator = jsonschema.Draft4Validator(meta_schema, resolver=resolver)
    validator.validate(schema_data)

    try:
        jsonschema.Draft4Validator.check_schema(schema_data)
        validator = jsonschema.Draft4Validator(meta_schema, resolver=resolver)
        validator.validate(schema_data)
    except jsonschema.ValidationError as e:
        return ValidationError(kind, filename, "VALIDATION_ERROR", e,
                               meta_schema_url)
    except (jsonschema.SchemaError,
            jsonschema.exceptions.RefResolutionError) as e:
        return ValidationError(kind, filename, "SCHEMA_ERROR", e,
                               meta_schema_url)

    return ValidationOK(kind, filename, meta_schema_url)


def validate_file(schemas_bundle, filename, data):
    kind = ValidatedFileKind.DATA_FILE

    logging.info('validating file: {}'.format(filename))

    try:
        schema_url = data[u'$schema']
    except KeyError as e:
        return ValidationError(kind, filename, "MISSING_SCHEMA_URL", e)

    if not schema_url.startswith('http') and not schema_url.startswith('/'):
        schema_url = '/' + schema_url

    schema = schemas_bundle[schema_url]

    try:
        resolver = jsonschema.RefResolver(
            schema_url,
            schema,
            handlers=get_handlers(schemas_bundle)
        )
        validator = jsonschema.Draft4Validator(schema, resolver=resolver)
        validator.validate(data)
    except jsonschema.ValidationError as e:
        return ValidationError(kind, filename, "VALIDATION_ERROR", e,
                               schema_url)
    except jsonschema.SchemaError as e:
        return ValidationError(kind, filename, "SCHEMA_ERROR", e, schema_url)
    except TypeError as e:
        return ValidationError(kind, filename, "SCHEMA_TYPE_ERROR", e,
                               schema_url)

    return ValidationOK(kind, filename, schema_url)


def fetch_schema(schema_url):
    if schema_url.startswith('http'):
        r = requests.get(schema_url)
        r.raise_for_status()
        schema = r.text
        return anymarkup.parse(schema, force_types=None)
    else:
        raise MissingSchemaFile(schema_url)


@click.command()
@click.option('--only-errors', is_flag=True, help='Print only errors')
@click.argument('schemas-bundle')
@click.argument('data-bundle')
def main(only_errors, schemas_bundle, data_bundle):
    bundle = json.load(open(data_bundle))
    schemas_bundle = json.load(open(schemas_bundle))

    # Validate schemas
    results_schemas = [
        validate_schema(schemas_bundle, filename, schema_data).dump()
        for filename, schema_data in schemas_bundle.items()
    ]

    results_files = [
        validate_file(schemas_bundle, filename, data).dump()
        for filename, data in bundle.items()
    ]

    # Calculate errors
    results = results_schemas + results_files

    errors = [
        r for r in results
        if r['result']['status'] == 'ERROR'
    ]

    # Output
    if only_errors:
        sys.stdout.write(json.dumps(errors, indent=4) + "\n")
    else:
        sys.stdout.write(json.dumps(results, indent=4) + "\n")

    if len(errors) > 0:
        sys.exit(1)
