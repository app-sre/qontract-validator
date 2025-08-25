import itertools
from collections import defaultdict
from collections.abc import Callable, Iterator
from enum import StrEnum
from functools import cache
from typing import Any, NamedTuple, NotRequired, TypedDict

import requests
from jsonschema import Draft6Validator, RefResolver, SchemaError, ValidationError
from yaml import YAMLError

from validator.bundle import Bundle, GraphqlTypeV2
from validator.jsonpath import JSONPath, JSONPathField, JSONPathIndex, build_jsonpath
from validator.traverse import Node, traverse_data
from validator.utils import load_yaml


class MissingSchemaFileError(Exception):
    def __init__(self, path):
        self.path = path
        message = f"schema not found: `{path}`"
        super(Exception, self).__init__(message)


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


class ValidationResult(TypedDict):
    filename: str
    kind: ValidatedFileKind
    result: _ValidationResult


class UniqueConstraintKey(NamedTuple):
    graphql_type: str
    graphql_field: str
    value: Any


class ContextUniqueConstraintKey(NamedTuple):
    filename: str
    jsonpath: str
    field_names: str
    identifier: str


def get_handlers(
    bundle: Bundle,
) -> dict[str, Callable]:
    def get_schema(uri: str) -> dict[str, Any]:
        return bundle.schemas[uri]

    return {"": get_schema}


@cache
def fetch_schema(schema_url: str) -> dict[str, Any]:
    if schema_url.startswith("http"):
        r = requests.get(schema_url, timeout=10)
        r.raise_for_status()
        return r.json()
    raise MissingSchemaFileError(schema_url)


def validate_schemas(bundle: Bundle) -> Iterator[ValidationResult]:
    for schema_path, schema in bundle.schemas.items():
        yield validate_schema(bundle, schema_path, schema)


def validate_schema(
    bundle: Bundle,
    schema_path: str,
    schema: dict[str, Any],
) -> ValidationResult:
    meta_schema_url = schema.get("$schema")
    if meta_schema_url is None:
        return ValidationResult(
            filename=schema_path,
            kind=ValidatedFileKind.SCHEMA,
            result=_ValidationResult(
                status=ValidationStatus.ERROR,
                reason="MISSING_SCHEMA_URL",
                summary=f"ERROR: {schema_path}",
                error=f"Missing schema URL in file {schema_path}",
            ),
        )
    meta_schema = bundle.schemas.get(meta_schema_url) or fetch_schema(meta_schema_url)
    resolver = RefResolver(schema_path, schema, handlers=get_handlers(bundle))
    try:
        Draft6Validator.check_schema(schema)
    except SchemaError as e:
        return ValidationResult(
            filename=schema_path,
            kind=ValidatedFileKind.SCHEMA,
            result=_ValidationResult(
                status=ValidationStatus.ERROR,
                reason="SCHEMA_ERROR",
                summary=f"ERROR: {schema_path}",
                error=str(e),
                schema_url=meta_schema_url,
            ),
        )
    try:
        validator = Draft6Validator(meta_schema, resolver=resolver)
        validator.validate(schema)
    except ValidationError as e:
        return ValidationResult(
            filename=schema_path,
            kind=ValidatedFileKind.SCHEMA,
            result=_ValidationResult(
                status=ValidationStatus.ERROR,
                reason="VALIDATION_ERROR",
                summary=f"ERROR: {schema_path}",
                error=str(e),
                schema_url=meta_schema_url,
            ),
        )

    return ValidationResult(
        filename=schema_path,
        kind=ValidatedFileKind.SCHEMA,
        result=_ValidationResult(
            status=ValidationStatus.OK,
            summary=f"OK: {schema_path} ({meta_schema_url})",
            schema_url=meta_schema_url,
        ),
    )


def validate_datafiles(bundle: Bundle) -> Iterator[ValidationResult]:
    for datafile_path, datafile in bundle.data.items():
        yield validate_file(bundle, datafile_path, datafile)

    unique_constraint: defaultdict[UniqueConstraintKey, list[str]] = defaultdict(list)
    context_unique_constraint: defaultdict[ContextUniqueConstraintKey, list[int]] = (
        defaultdict(list)
    )

    for node in traverse_data(bundle):
        filename = node.path
        if (
            isinstance(node.data, str)
            and node.is_resource_ref()
            and node.data not in bundle.resources
        ):
            yield ValidationResult(
                filename=filename,
                kind=ValidatedFileKind.REF,
                result=_ValidationResult(
                    status=ValidationStatus.ERROR,
                    summary=f"ERROR: {filename}",
                    reason="RESOURCE_FILE_NOT_FOUND",
                    error=f"Resource file {node.data} not found in file {filename}",
                    schema_url=node.schema_path or "",
                ),
            )

        match node.jsonpaths:
            case [*_, JSONPathField("$ref")]:
                yield validate_ref(node)

        if unique_constraint_key := build_unique_constraint_key_from_node(node):
            unique_constraint[unique_constraint_key].append(filename)

        match node.jsonpaths:
            case [*_, JSONPathIndex(index), JSONPathField(field)]:
                if (
                    context_unique_constraint_key
                    := build_context_unique_constraint_key_from_node(node, field)
                ):
                    context_unique_constraint[context_unique_constraint_key].append(
                        index
                    )

    for unique_key, filenames in unique_constraint.items():
        if len(filenames) > 1:
            sorted_filenames = sorted(filenames)
            filename = sorted_filenames[0]
            yield ValidationResult(
                filename=filename,
                kind=ValidatedFileKind.UNIQUE,
                result=_ValidationResult(
                    status=ValidationStatus.ERROR,
                    summary=f"ERROR: {filename}",
                    reason="DUPLICATE_UNIQUE_FIELD",
                    error=f"The field '{unique_key.graphql_field}' is repeated: {', '.join(sorted_filenames)}",
                ),
            )

    for context_unique_key, indices in context_unique_constraint.items():
        if len(indices) > 1:
            filename = context_unique_key.filename
            duplicates = ", ".join(
                f"{context_unique_key.jsonpath}/{index}" for index in indices
            )
            yield ValidationResult(
                filename=filename,
                kind=ValidatedFileKind.UNIQUE,
                result=_ValidationResult(
                    status=ValidationStatus.ERROR,
                    summary=f"ERROR: {filename}",
                    reason="DUPLICATE_CONTEXT_UNIQUE_FIELD",
                    error=f"Context uniqueness error, file: {filename}, fields: {context_unique_key.field_names}, duplicates: {duplicates}",
                ),
            )


def build_unique_constraint_key_from_node(node: Node) -> UniqueConstraintKey | None:
    if (
        (graphql_type := node.graphql_type)
        and (graphql_field := node.graphql_field)
        and graphql_field.get("isUnique")
    ):
        return UniqueConstraintKey(graphql_type.name, graphql_field["name"], node.data)
    return None


def build_context_unique_constraint_key(
    filename: str,
    jsonpaths: list[JSONPath],
    identifier: str,
    graphql_type: GraphqlTypeV2,
) -> ContextUniqueConstraintKey | None:
    context_unique_field_names = graphql_type.context_unique_field_names()
    field_names = ", ".join(sorted(context_unique_field_names))
    return ContextUniqueConstraintKey(
        filename=filename,
        jsonpath=build_jsonpath(jsonpaths),
        field_names=field_names,
        identifier=identifier,
    )


def build_context_unique_constraint_key_from_node(
    node: Node,
    field: str,
) -> ContextUniqueConstraintKey | None:
    match field:
        case "$ref":
            if (
                (data := node.resolve_ref())
                and (identifier := data.get("__identifier"))
                and (schema_path := data.get("$schema"))
                and (
                    graphql_type := node.bundle.graphql_lookup.get_by_schema(
                        schema_path
                    )
                )
            ):
                return build_context_unique_constraint_key(
                    filename=node.path,
                    jsonpaths=node.jsonpaths[:-2],
                    identifier=identifier,
                    graphql_type=graphql_type,
                )
        case "__identifier":
            if graphql_type := node.graphql_type:
                return build_context_unique_constraint_key(
                    filename=node.path,
                    jsonpaths=node.jsonpaths[:-2],
                    identifier=node.data,
                    graphql_type=graphql_type,
                )
    return None


def validate_ref(node: Node) -> ValidationResult:
    filename = node.path
    ref = node.data
    ref_data = node.bundle.data.get(ref)
    if ref_data is None:
        return ValidationResult(
            filename=filename,
            kind=ValidatedFileKind.REF,
            result=_ValidationResult(
                status=ValidationStatus.ERROR,
                summary=f"ERROR: {filename}",
                reason="FILE_NOT_FOUND",
                error=f"Reference to file {ref} in file {filename} not found",
            ),
        )

    if (
        (ref_data_schema := ref_data.get("$schema"))
        and node.schema
        and (expected_schema := node.schema.get("$schemaRef"))
    ):
        if isinstance(expected_schema, str):
            if expected_schema != ref_data_schema:
                return ValidationResult(
                    filename=filename,
                    kind=ValidatedFileKind.REF,
                    result=_ValidationResult(
                        status=ValidationStatus.ERROR,
                        summary=f"ERROR: {filename}",
                        reason="INCORRECT_SCHEMA",
                        error=f"incorrect schema: got `{ref_data_schema}`, expecting `{expected_schema}`",
                    ),
                )
        else:
            try:
                validator = Draft6Validator(expected_schema)
                validator.validate(ref_data)
            except ValidationError as e:
                return ValidationResult(
                    filename=filename,
                    kind=ValidatedFileKind.REF,
                    result=_ValidationResult(
                        status=ValidationStatus.ERROR,
                        summary=f"ERROR: {filename}",
                        reason="SCHEMA_REF_VALIDATION_ERROR",
                        error=str(e),
                    ),
                )

    schema_url = node.schema_path or ""
    return ValidationResult(
        filename=filename,
        kind=ValidatedFileKind.REF,
        result=_ValidationResult(
            status=ValidationStatus.OK,
            summary=f"OK: {filename} ({ref}) ({schema_url})",
            schema_url=schema_url,
        ),
    )


def validate_file(
    bundle: Bundle,
    filename: str,
    data: dict[str, Any],
) -> ValidationResult:
    schema_url = data.get("$schema")
    if schema_url is None:
        return ValidationResult(
            filename=filename,
            kind=ValidatedFileKind.DATA_FILE,
            result=_ValidationResult(
                status=ValidationStatus.ERROR,
                summary=f"ERROR: {filename}",
                reason="MISSING_SCHEMA_URL",
                error=f"Missing schema URL in file {filename}",
            ),
        )

    normalized_schema_url = (
        "/" + schema_url
        if not schema_url.startswith("http") and not schema_url.startswith("/")
        else schema_url
    )

    schema = bundle.schemas.get(normalized_schema_url)
    if schema is None:
        return ValidationResult(
            filename=filename,
            kind=ValidatedFileKind.DATA_FILE,
            result=_ValidationResult(
                status=ValidationStatus.ERROR,
                summary=f"ERROR: {filename}",
                reason="SCHEMA_NOT_FOUND",
                error=f"Schema {normalized_schema_url} not found in the file {filename}",
                schema_url=normalized_schema_url,
            ),
        )

    resolver = RefResolver(schema_url, schema, handlers=get_handlers(bundle))
    try:
        validator = Draft6Validator(schema, resolver=resolver)
        validator.validate(data)
    except ValidationError as e:
        return ValidationResult(
            filename=filename,
            kind=ValidatedFileKind.DATA_FILE,
            result=_ValidationResult(
                status=ValidationStatus.ERROR,
                reason="VALIDATION_ERROR",
                summary=f"ERROR: {filename}",
                error=str(e),
                schema_url=schema_url,
            ),
        )

    return ValidationResult(
        filename=filename,
        kind=ValidatedFileKind.DATA_FILE,
        result=_ValidationResult(
            status=ValidationStatus.OK,
            summary=f"OK: {filename} ({schema_url})",
            schema_url=schema_url,
        ),
    )


def validate_resources(bundle: Bundle) -> Iterator[ValidationResult]:
    for resource_path, resource in bundle.resources.items():
        yield validate_resource(bundle, resource_path, resource)


def validate_resource(
    bundle: Bundle,
    resource_path: str,
    resource: dict[str, Any],
) -> ValidationResult:
    if resource["$schema"] is None:
        return ValidationResult(
            filename=resource_path,
            kind=ValidatedFileKind.NONE,
            result=_ValidationResult(
                status=ValidationStatus.OK,
                summary=f"OK: {resource_path} ()",
                schema_url="",
            ),
        )

    try:
        data = load_yaml(resource["content"])
    except YAMLError:
        return ValidationResult(
            filename=resource_path,
            kind=ValidatedFileKind.NONE,
            result=_ValidationResult(
                status=ValidationStatus.OK,
                summary=f"OK: {resource_path} ()",
                schema_url="",
            ),
        )

    return validate_file(bundle, resource_path, data)


def validate_graphql(bundle: Bundle) -> Iterator[ValidationResult]:
    if isinstance(bundle.graphql, dict):
        yield validate_file(
            bundle=bundle,
            filename="graphql-schemas/schema.yml",
            data=bundle.graphql,
        )


def validate_bundle(
    bundle: Bundle,
) -> list[ValidationResult]:
    return list(
        itertools.chain(
            validate_schemas(bundle),
            validate_datafiles(bundle),
            validate_resources(bundle),
            validate_graphql(bundle),
        )
    )
