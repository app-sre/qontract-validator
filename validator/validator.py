import contextlib
import itertools
import json
import logging
import sys
from collections import defaultdict
from collections.abc import Callable, Iterator
from enum import StrEnum
from functools import cache
from typing import IO, Any, NotRequired, TypedDict

import click
import jsonschema
import requests
import yaml
from jsonschema import Draft6Validator

from validator.bundle import (
    Bundle,
    load_bundle,
)
from validator.utils import load_yaml

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.WARNING)


class IncorrectSchemaError(Exception):
    def __init__(self, got, expecting):
        message = f"incorrect schema: got `{got}`, expecting `{expecting}`"
        super(Exception, self).__init__(message)


class MissingSchemaFileError(Exception):
    def __init__(self, path):
        self.path = path
        message = f"schema not found: `{path}`"
        super(Exception, self).__init__(message)


class DuplicateUniqueFieldError(Exception):
    pass


class NotFoundError(Exception):
    pass


class ValidatedFileKind(StrEnum):
    SCHEMA = "SCHEMA"
    DATA_FILE = "FILE"
    REF = "REF"
    NONE = "NONE"
    UNIQUE = "UNIQUE"


class ValidationStatus(StrEnum):
    OK = "OK"
    ERROR = "ERROR"


class _ValidationResult(TypedDict):
    summary: str
    status: ValidationStatus
    schema_url: NotRequired[str]
    reason: NotRequired[str]
    error: NotRequired[str]
    ref: NotRequired[str]
    ptr: NotRequired[str]
    meta_schema_url: NotRequired[str]


class ValidationResult(TypedDict):
    filename: str
    kind: ValidatedFileKind
    ref: NotRequired[str]
    result: _ValidationResult


class ValidationOK:
    def __init__(
        self,
        kind: ValidatedFileKind,
        filename: str,
        schema_url: str,
    ) -> None:
        self.kind = kind
        self.filename = filename
        self.schema_url = schema_url
        self.summary = f"OK: {self.filename} ({self.schema_url})"

    def dump(self) -> ValidationResult:
        return ValidationResult(
            filename=self.filename,
            kind=self.kind,
            result=_ValidationResult(
                summary=self.summary,
                status=ValidationStatus.OK,
                schema_url=self.schema_url,
            ),
        )


class ValidationRefOK:
    def __init__(
        self,
        kind: ValidatedFileKind,
        filename: str,
        ref: str,
        schema_url: str,
    ) -> None:
        self.kind = kind
        self.filename = filename
        self.schema_url = schema_url
        self.ref = ref
        self.summary = f"OK: {self.filename} ({self.ref}) ({self.schema_url})"

    def dump(self) -> ValidationResult:
        return ValidationResult(
            filename=self.filename,
            kind=self.kind,
            ref=self.ref,
            result=_ValidationResult(
                summary=self.summary,
                status=ValidationStatus.OK,
                schema_url=self.schema_url,
                ref=self.ref,
            ),
        )


class ValidationError:
    def __init__(
        self,
        kind: ValidatedFileKind,
        filename: str,
        reason: str,
        error: Exception,
        *,
        meta_schema_url: str | None = None,
        ref: str | None = None,
        schema_url: str | None = None,
        ptr: str | None = None,
    ) -> None:
        self.kind = kind
        self.filename = filename
        self.reason = reason
        self.error = error
        self.meta_schema_url = meta_schema_url
        self.ref = ref
        self.schema_url = schema_url
        self.ptr = ptr
        self.summary = f"ERROR: {self.filename}"

    def dump(self):
        return ValidationResult(
            filename=self.filename,
            kind=self.kind,
            result=_ValidationResult(
                summary=self.summary,
                status=ValidationStatus.ERROR,
                reason=self.reason,
                error=str(self.error),
                meta_schema_url=self.meta_schema_url,
                ref=self.ref,
                schema_url=self.schema_url,
                ptr=self.ptr,
            ),
        )


def get_handlers(
    schemas_bundle: dict[str, dict[str, Any]],
) -> dict[str, Callable]:
    def get_schema(uri: str) -> dict[str, Any]:
        return schemas_bundle[uri]

    return {"": get_schema}


def validate_schema(
    schemas_bundle: dict[str, dict[str, Any]],
    filename: str,
    schema_data: dict[str, Any],
) -> ValidationError | ValidationOK:
    kind = ValidatedFileKind.SCHEMA

    logging.info("validating schema: %s", filename)

    meta_schema_url = schema_data.get("$schema")
    if meta_schema_url is None:
        return ValidationError(
            kind,
            filename,
            "MISSING_SCHEMA_URL",
            NotFoundError(f"Missing schema URL in file {filename}"),
        )

    meta_schema = schemas_bundle.get(meta_schema_url)
    if meta_schema is None:
        meta_schema = fetch_schema(meta_schema_url)

    resolver = jsonschema.RefResolver(
        filename, schema_data, handlers=get_handlers(schemas_bundle)
    )

    try:
        Draft6Validator.check_schema(schema_data)
        validator = Draft6Validator(meta_schema, resolver=resolver)
        validator.validate(schema_data)
    except jsonschema.ValidationError as e:
        return ValidationError(
            kind, filename, "VALIDATION_ERROR", e, meta_schema_url=meta_schema_url
        )
    except (jsonschema.SchemaError, jsonschema.exceptions.RefResolutionError) as e:
        return ValidationError(
            kind, filename, "SCHEMA_ERROR", e, meta_schema_url=meta_schema_url
        )

    return ValidationOK(kind, filename, meta_schema_url)


def validate_file(
    schemas_bundle: dict[str, dict[str, Any]],
    filename: str,
    data: dict[str, Any],
) -> ValidationError | ValidationOK:
    kind = ValidatedFileKind.DATA_FILE

    logging.info("validating file: %s", filename)

    schema_url = data.get("$schema")
    if schema_url is None:
        return ValidationError(
            kind,
            filename,
            "MISSING_SCHEMA_URL",
            NotFoundError(f"Missing schema URL in file {filename}"),
        )

    if not schema_url.startswith("http") and not schema_url.startswith("/"):
        schema_url = "/" + schema_url

    schema = schemas_bundle.get(schema_url)
    if schema is None:
        return ValidationError(
            kind,
            filename,
            "SCHEMA_NOT_FOUND",
            NotFoundError(f"Schema {schema_url} not found in the file {filename}"),
            schema_url=schema_url,
        )

    try:
        resolver = jsonschema.RefResolver(
            schema_url, schema, handlers=get_handlers(schemas_bundle)
        )
        validator = Draft6Validator(schema, resolver=resolver)
        validator.validate(data)
    except jsonschema.ValidationError as e:
        return ValidationError(
            kind, filename, "VALIDATION_ERROR", e, schema_url=schema_url
        )
    except jsonschema.SchemaError as e:
        return ValidationError(kind, filename, "SCHEMA_ERROR", e, schema_url=schema_url)
    except TypeError as e:
        return ValidationError(
            kind, filename, "SCHEMA_TYPE_ERROR", e, schema_url=schema_url
        )

    return ValidationOK(kind, filename, schema_url)


def _get_unique_field_names(gql_fields: list[dict[str, Any]]) -> list[str]:
    return [field["name"] for field in gql_fields if field.get("isUnique")]


def validate_unique_fields(
    bundle: Bundle,
) -> Iterator[ValidationError]:
    graphql = {
        item.spec["name"]: item.spec["fields"] for item in bundle.list_graphql_types()
    }
    datafiles_map = {
        field["type"]: datafileSchema
        for field in graphql["Query"]
        if (datafileSchema := field.get("datafileSchema"))
    }

    unique_map = {
        datafileSchema: _get_unique_field_names(gql_fields)
        for gql_type, gql_fields in graphql.items()
        if gql_type != "Query" and (datafileSchema := datafiles_map.get(gql_type))
    }

    unique_fields = defaultdict(list)
    for filename, data in bundle.data.items():
        if schema := data.get("$schema"):
            for field in unique_map.get(schema, []):
                key = (schema, field, data.get(field))
                unique_fields[key].append(filename)

    for (schema, field, _), filenames in unique_fields.items():
        if len(filenames) > 1:
            sorted_filenames = sorted(filenames)
            yield ValidationError(
                ValidatedFileKind.UNIQUE,
                sorted_filenames[0],
                "DUPLICATE_UNIQUE_FIELD",
                DuplicateUniqueFieldError(
                    f"The field '{field}' is repeated: {', '.join(sorted_filenames)}",
                ),
                ref=schema,
                ptr=field,
            )


def validate_resource(
    schemas_bundle: dict[str, dict[str, Any]],
    filename: str,
    resource: dict[str, Any],
) -> ValidationError | ValidationOK:
    if resource["$schema"] is None:
        return ValidationOK(ValidatedFileKind.NONE, filename, "")

    try:
        data = load_yaml(resource["content"])
    except yaml.error.YAMLError:
        logging.warning("We can't validate resource with schema %s", filename)
        return ValidationOK(ValidatedFileKind.NONE, filename, "")

    return validate_file(schemas_bundle, filename, data)


def validate_ref(
    schemas_bundle: dict[str, dict[str, Any]],
    bundle: dict[str, dict[str, Any]],
    filename: str,
    data: dict[str, Any],
    ptr: str,
    ref: dict[str, Any],
) -> Iterator[ValidationError | ValidationRefOK | ValidationOK]:
    kind = ValidatedFileKind.REF

    ref_data = bundle.get(ref["$ref"])
    if ref_data is None:
        yield ValidationError(
            kind,
            filename,
            "FILE_NOT_FOUND",
            NotFoundError(
                f"Reference to file {ref['$ref']} in file {filename} not found"
            ),
            ref=ref["$ref"],
        )
        return

    schema = schemas_bundle.get(data["$schema"])
    if schema is None:
        yield ValidationError(
            kind,
            filename,
            "SCHEMA_NOT_FOUND",
            NotFoundError(
                f"Reference to schema {ref['$ref']} in file {filename} not found"
            ),
            ref=ref["$ref"],
        )
        return

    try:
        schema_infos = get_schema_info_from_pointer(schema, ptr, schemas_bundle)
    except KeyError as e:
        yield ValidationError(
            kind,
            filename,
            "SCHEMA_DEFINITION_NOT_FOUND",
            e,
            ref=ref["$ref"],
            ptr=ptr,
        )
        return

    for schema_info in schema_infos:
        if expected_schema := schema_info.get("$schemaRef"):
            if isinstance(expected_schema, str):
                if expected_schema != ref_data["$schema"]:
                    yield ValidationError(
                        kind,
                        filename,
                        "INCORRECT_SCHEMA",
                        IncorrectSchemaError(ref_data["$schema"], expected_schema),
                        ref=ref["$ref"],
                    )
                else:
                    yield ValidationRefOK(kind, filename, ref["$ref"], data["$schema"])
                    return
            else:
                try:
                    validator = Draft6Validator(expected_schema)
                    validator.validate(ref_data)
                    yield ValidationRefOK(kind, filename, ref["$ref"], data["$schema"])
                    return
                except jsonschema.exceptions.ValidationError as e:
                    yield ValidationError(
                        kind, filename, "SCHEMA_REF_VALIDATION_ERROR", e
                    )


@cache
def fetch_schema(schema_url: str) -> dict[str, Any]:
    if schema_url.startswith("http"):
        r = requests.get(schema_url, timeout=10)
        r.raise_for_status()
        return r.json()
    raise MissingSchemaFileError(schema_url)


def find_refs(
    obj: Any,
    ptr: str = "",
) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(obj, dict):
        if "$ref" in obj:
            yield ptr, obj
        else:
            for key, item in obj.items():
                new_ptr = f"{ptr}/{key}"
                yield from find_refs(item, new_ptr)
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            new_ptr = f"{ptr}/{index}"
            yield from find_refs(item, new_ptr)


def _get_external_schema_ref(info: dict[str, Any]) -> str | None:
    if (ref := info.get("$ref")) and ref != "/common-1.json#/definitions/crossref":
        return ref
    return None


def get_schema_info_from_pointer(
    schema: dict[str, Any],
    ptr: str,
    schemas_bundle: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    info = schema

    ptr_chunks = ptr.split("/")[1:]
    for idx, chunk in enumerate(ptr_chunks):
        info = info["items"] if chunk.isdigit() else info["properties"][chunk]

        if ref := _get_external_schema_ref(info):
            # this points to an external schema
            # we need to load it
            info = schemas_bundle[ref]
        elif list(info.keys()) == ["oneOf"]:
            schemas = []
            # this is a list of type options in an array
            # we look at all of them and try to find at least one where the
            # ptr resolves successfully
            for item in info["oneOf"]:
                with contextlib.suppress(KeyError):
                    schemas.extend(
                        get_schema_info_from_pointer(
                            schemas_bundle[item["$ref"]],
                            f"/{'/'.join(ptr_chunks[idx + 1 :])}",
                            schemas_bundle,
                        )
                    )
                    # this subtype is not the one we are looking for
                with contextlib.suppress(KeyError):
                    schemas.append(schemas_bundle[item["$schemaRef"]])
            if not schemas:
                msg = (
                    f"unable to resolve schema for {ptr} "
                    f"in oneOf options {info['oneOf']}"
                )
                raise KeyError(msg)
            return schemas

    return [info]


def validate_bundle(
    bundle: Bundle,
) -> list[ValidationResult]:
    # Validate schemas
    results_schemas = (
        validate_schema(bundle.schemas, filename, schema_data)
        for filename, schema_data in bundle.schemas.items()
    )

    # validate datafiles
    results_files = (
        validate_file(bundle.schemas, filename, data)
        for filename, data in bundle.data.items()
    )

    # validate unique fields
    results_unique_fields = validate_unique_fields(bundle)

    # validate resources
    results_resources = (
        validate_resource(bundle.schemas, filename, resource)
        for filename, resource in bundle.resources.items()
    )

    # validate refs
    results_refs = (
        result
        for filename, data in bundle.data.items()
        for ptr, ref in find_refs(data)
        for result in validate_ref(
            bundle.schemas, bundle.data, filename, data, ptr, ref
        )
    )

    results_graphql_schemas = (
        [validate_file(bundle.schemas, "graphql-schemas/schema.yml", bundle.graphql)]
        if isinstance(bundle.graphql, dict)
        else []
    )

    return [
        result.dump()
        for result in itertools.chain(
            results_schemas,
            results_files,
            results_unique_fields,
            results_resources,
            results_refs,
            results_graphql_schemas,
        )
    ]


@click.command()
@click.option("--only-errors", is_flag=True, help="Print only errors")
@click.argument("bundlefile", type=click.File("rb"))
def main(
    *,
    only_errors: bool,
    bundlefile: IO,
) -> None:
    bundle = load_bundle(bundlefile)

    results = validate_bundle(bundle)

    # Calculate errors
    errors = [r for r in results if r["result"]["status"] == ValidationStatus.ERROR]

    # Output
    if only_errors:
        sys.stdout.write(json.dumps(errors, indent=2) + "\n")
    else:
        sys.stdout.write(json.dumps(results, indent=2) + "\n")

    if len(errors) > 0:
        sys.exit(1)
