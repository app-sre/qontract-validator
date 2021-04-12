import json
import yaml
import logging
import sys

from enum import Enum
from functools import lru_cache

import click
import jsonschema
from jsonschema import Draft6Validator as jsonschema_validator
import requests


logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.WARNING)

try:
    basestring
except NameError:
    basestring = str


class IncorrectSchema(Exception):
    def __init__(self, got, expecting):
        message = "incorrect schema: got `{}`, expecting `{}`".format(
            got, expecting)
        super(Exception, self).__init__(message)


class MissingSchemaFile(Exception):
    def __init__(self, path):
        self.path = path
        message = "schema not found: `{}`".format(path)
        super(Exception, self).__init__(message)


class ValidatedFileKind(Enum):
    SCHEMA = "SCHEMA"
    DATA_FILE = "FILE"
    REF = "REF"
    NONE = "NONE"
    UNIQUE = "UNIQUE"


class ValidationOK():
    status = True

    def __init__(self, kind, filename, schema_url):
        self.kind = kind
        self.filename = filename
        self.schema_url = schema_url
        self.summary = "OK: {} ({})".format(self.filename, self.schema_url)

    def dump(self):
        return {
            "filename": self.filename,
            "kind": self.kind.value,
            "result": {
                "summary": self.summary,
                "status": "OK",
                "schema_url": self.schema_url,
            }
        }


class ValidationRefOK():
    status = True

    def __init__(self, kind, filename, ref, schema_url):
        self.kind = kind
        self.filename = filename
        self.schema_url = schema_url
        self.ref = ref
        self.summary = "OK: {} ({}) ({})".format(self.filename,
                                                 self.ref,
                                                 self.schema_url)

    def dump(self):
        return {
            "filename": self.filename,
            "ref": self.ref,
            "kind": self.kind.value,
            "result": {
                "summary": self.summary,
                "status": "OK",
                "schema_url": self.schema_url,
                "ref": self.ref,
            }
        }


class ValidationError():
    status = False

    def __init__(self, kind, filename, reason, error, **kwargs):
        self.kind = kind
        self.filename = filename
        self.reason = reason
        self.error = error
        self.kwargs = kwargs
        self.summary = "ERROR: {}".format(self.filename)

    def dump(self):
        result = {
            "summary": self.summary,
            "status": "ERROR",
            "reason": self.reason,
            "error": self.error.__str__()
        }

        result.update(self.kwargs)

        return {
            "filename": self.filename,
            "kind": self.kind.value,
            "result": result
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
        '': lambda x: schemas_bundle[x]
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

    resolver = jsonschema.RefResolver(
        filename,
        schema_data,
        handlers=get_handlers(schemas_bundle)
    )

    try:
        jsonschema_validator.check_schema(schema_data)
        validator = jsonschema_validator(meta_schema, resolver=resolver)
        validator.validate(schema_data)
    except jsonschema.ValidationError as e:
        return ValidationError(kind, filename, "VALIDATION_ERROR", e,
                               meta_schema_url=meta_schema_url)
    except (jsonschema.SchemaError,
            jsonschema.exceptions.RefResolutionError) as e:
        return ValidationError(kind, filename, "SCHEMA_ERROR", e,
                               meta_schema_url=meta_schema_url)

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

    try:
        schema = schemas_bundle[schema_url]
    except KeyError as e:
        return ValidationError(kind, filename, "SCHEMA_NOT_FOUND", e,
                               schema_url=schema_url)

    try:
        resolver = jsonschema.RefResolver(
            schema_url,
            schema,
            handlers=get_handlers(schemas_bundle)
        )
        validator = jsonschema_validator(schema, resolver=resolver)
        validator.validate(data)
    except jsonschema.ValidationError as e:
        return ValidationError(kind, filename, "VALIDATION_ERROR", e,
                               schema_url=schema_url)
    except jsonschema.SchemaError as e:
        return ValidationError(kind, filename, "SCHEMA_ERROR", e,
                               schema_url=schema_url)
    except TypeError as e:
        return ValidationError(kind, filename, "SCHEMA_TYPE_ERROR", e,
                               schema_url=schema_url)

    return ValidationOK(kind, filename, schema_url)


def validate_unique_fields(graphql_bundle, data_bundle):
    graphql = {}
    for item in graphql_bundle:
        graphql[item['name']] = item['fields']

    datafiles_map = {}
    for field in graphql['Query']:
        if 'datafileSchema' in field:
            datafiles_map[field['type']] = field['datafileSchema']

    unique_map = {}
    for gql_type, gql_fields in graphql.items():
        if gql_type == 'Query':
            continue

        datafile_schema = datafiles_map.get(gql_type)
        if not datafile_schema:
            # not top-level schema
            continue

        unique_map[datafile_schema] = []
        for field in gql_fields:
            if field.get('isUnique'):
                unique_map[datafile_schema].append(field['name'])

    unique_fields = {}
    for filename, data in data_bundle.items():
        for field in unique_map.get(data['$schema'], []):
            key = (data['$schema'], field, data.get(field))
            unique_fields.setdefault(key, [])
            unique_fields[key].append(filename)

    results = []
    for key, filenames in unique_fields.items():
        if len(filenames) > 1:
            error = ValidationError(
                ValidatedFileKind.UNIQUE,
                filenames[0],
                "DUPLICATE_UNIQUE_FIELD",
                "The field '{}' is repeated: {}".format(key[1], filenames))
            results.append(error.dump())

    return results


def validate_resource(schemas_bundle, filename, resource):
    content = resource['content']
    if '$schema' not in content:
        return ValidationOK(ValidatedFileKind.NONE, filename, '')

    try:
        data = yaml.load(content, Loader=yaml.FullLoader)
    except yaml.error.YAMLError:
        logging.warning(f"We can't validate resource with schema {filename}")
        return ValidationOK(ValidatedFileKind.NONE, filename, '')

    return validate_file(schemas_bundle, filename, data)


def validate_ref(schemas_bundle, bundle, filename, data, ptr, ref):
    kind = ValidatedFileKind.REF

    try:
        ref_data = bundle[ref["$ref"]]
    except KeyError as e:
        return ValidationError(
            kind,
            filename,
            "FILE_NOT_FOUND",
            e,
            ref=ref['$ref']
        )

    try:
        schema = schemas_bundle[data['$schema']]
    except KeyError as e:
        return ValidationError(
            kind,
            filename,
            "SCHEMA_NOT_FOUND",
            e,
            ref=ref['$ref']
        )

    try:
        schema_info = get_schema_info_from_pointer(schema, ptr, schemas_bundle)
    except KeyError as e:
        return ValidationError(
            kind,
            filename,
            "SCHEMA_DEFINITION_NOT_FOUND",
            e,
            ref=ref['$ref']
        )

    expected_schema = schema_info.get('$schemaRef')

    if expected_schema is not None:
        if isinstance(expected_schema, basestring):
            if expected_schema != ref_data['$schema']:
                return ValidationError(
                    kind,
                    filename,
                    "INCORRECT_SCHEMA",
                    IncorrectSchema(ref_data['$schema'], expected_schema),
                    ref=ref['$ref']
                )
        else:
            try:
                validator = jsonschema_validator(expected_schema)
                validator.validate(ref_data)
            except jsonschema.exceptions.ValidationError as e:
                return ValidationError(kind, filename,
                                       "SCHEMA_REF_VALIDATION_ERROR", e)

    return ValidationRefOK(kind, filename, ref['$ref'], data['$schema'])


@lru_cache()
def fetch_schema(schema_url):
    if schema_url.startswith('http'):
        r = requests.get(schema_url)
        r.raise_for_status()
        schema = r.text
        return json.loads(schema)
    else:
        raise MissingSchemaFile(schema_url)


def find_refs(obj, ptr=None, refs=None):
    if refs is None:
        refs = []

    if ptr is None:
        ptr = ""

    if isinstance(obj, dict):
        # is this a ref?
        if '$ref' in obj:
            refs.append((ptr, obj))
        else:
            for key, item in obj.items():
                new_ptr = "{}/{}".format(ptr, key)
                find_refs(item, new_ptr, refs)
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            new_ptr = "{}/{}".format(ptr, index)
            find_refs(item, new_ptr, refs)

    return refs


def get_schema_info_from_pointer(schema, ptr, schemas_bundle):
    info = schema

    for chunk in ptr.split("/")[1:]:
        if chunk.isdigit():
            info = info['items']
            if list(info.keys()) == ['$ref']:
                # this points to an external schema
                # we need to load it
                info = schemas_bundle[info['$ref']]
        else:
            info = info['properties'][chunk]

    return info


@click.command()
@click.option('--only-errors', is_flag=True, help='Print only errors')
@click.argument('bundle', type=click.File('rb'))
def main(only_errors, bundle):
    bundle = json.load(bundle)

    data_bundle = bundle['data']
    schemas_bundle = bundle['schemas']
    resources_bundle = bundle['resources']
    graphql_bundle = bundle['graphql']

    # Validate schemas
    results_schemas = [
        validate_schema(schemas_bundle, filename, schema_data).dump()
        for filename, schema_data in schemas_bundle.items()
    ]

    # validate datafiles
    results_files = [
        validate_file(schemas_bundle, filename, data).dump()
        for filename, data in data_bundle.items()
    ]

    # validate unique fields
    results_unique_fields = validate_unique_fields(graphql_bundle, data_bundle)

    # validate resources
    results_resources = [
        validate_resource(schemas_bundle, filename, resource).dump()
        for filename, resource in resources_bundle.items()
    ]

    # validate refs
    results_refs = [
        validate_ref(schemas_bundle, data_bundle,
                     filename, data, ptr, ref).dump()
        for filename, data in data_bundle.items()
        for ptr, ref in find_refs(data)
    ]

    # Calculate errors
    results = results_schemas + results_files + results_unique_fields + \
        results_resources + results_refs
    errors = list(filter(lambda x: x['result']['status'] == 'ERROR', results))

    # Output
    if only_errors:
        sys.stdout.write(json.dumps(errors, indent=4) + "\n")
    else:
        sys.stdout.write(json.dumps(results, indent=4) + "\n")

    if len(errors) > 0:
        sys.exit(1)
