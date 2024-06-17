import hashlib
from collections.abc import Hashable
from contextlib import contextmanager
from typing import Any

from jsonpath_ng.ext import parse

from validator.bundle import (
    Bundle,
    GraphqlType,
)

RESOURCE_REF = "/common-1.json#/definitions/resourceref"
CROSS_REF = "/common-1.json#/definitions/crossref"


class SchemaTraversalLoopException(Exception):
    pass


class Context:
    def __init__(self, bundle: Bundle):
        self.bundle = bundle
        self.datafile_schema_resource_ref_paths: dict[str, list[str]] = {}
        self.datafile_object_identifier_paths: dict = {}
        self.schema_path: list[str] = []

    @contextmanager
    def step_into(self, datafile_schema: str):
        try:
            self.schema_path.append(datafile_schema)
            yield
        finally:
            self.schema_path.pop()


def itemgetter(properties, obj):
    def to_hashable(field):
        if isinstance(field, Hashable):
            return field
        else:
            return repr(field)

    if len(properties) == 1:
        item = properties[0]
        return to_hashable(obj.get(item))
    else:
        id = tuple(to_hashable(obj.get(item)) for item in properties)
        if set(id) == {None}:
            return None
        else:
            return id


def resolve_object_value(object_value: Any, bundle: Bundle) -> Any:
    if isinstance(object_value, dict) and "$ref" in object_value:
        return bundle.data.get(object_value["$ref"])
    return object_value


def ensure_context_uniqueness(
    df, df_path: str, config: list, bundle: Bundle
) -> list[str]:
    errors = []
    for jsonpath, (identifier, sub_paths) in config:
        ids_in_context = set()
        for object in jsonpath.find(df):
            object_value = resolve_object_value(object.value, bundle)
            object_context_id = itemgetter(identifier, object_value)
            if object_context_id is None:
                continue
            if object_context_id in ids_in_context:
                errors.append(
                    f"context uniqueness error - file: {df_path}, "
                    f"path: {str(object.full_path)}, identifier = {identifier}, "
                    f"value = {object_context_id}"
                )
            else:
                ids_in_context.add(object_context_id)
                hash_id = hashlib.md5()
                for i in object_context_id:
                    hash_id.update(str(i).encode())
                object.value["__identifier"] = hash_id.hexdigest()
            if sub_paths:
                errors.extend(
                    ensure_context_uniqueness(object_value, df_path, sub_paths, bundle)
                )
    return errors


def postprocess_bundle(
    bundle: Bundle, checksum_field_name: str | None = None
) -> list[str]:
    # build up a list of resource references on a type level
    context = Context(bundle)

    # inject $sha256sum field to datafile schemas
    if checksum_field_name:
        for s in bundle.schemas.values():
            if s["$schema"] == "/metaschema-1.json":
                s["properties"][checksum_field_name] = {
                    "type": "string",
                    "description": "sha256sum of the datafile",
                }

    # find all jsonpath to resource reference fields in the schemas
    datafile_schema_resource_ref_jsonpaths: dict[str, list] = {}
    datafile_schema_object_identifier_jsonpaths: dict[str, dict] = {}
    for datafile_schema, schema_object in bundle.schemas.items():
        graphql_type = bundle.get_graphql_type_for_schema(datafile_schema)
        if not graphql_type:
            continue
        paths, object_identifier, _ = process_data_file_schema_object(
            datafile_schema, schema_object, graphql_type, context
        )
        datafile_schema_resource_ref_jsonpaths[datafile_schema] = [
            parse(p) for p in paths
        ]
        datafile_schema_object_identifier_jsonpaths[datafile_schema] = [
            (parse(path), properties) for path, properties in object_identifier.items()
        ]

    # use the jsonpaths to find actual resources and backref them to their data files
    errors = []
    for df_path, df in bundle.data.items():
        df_schema = df["$schema"]
        errors.extend(
            ensure_context_uniqueness(
                df,
                df_path,
                datafile_schema_object_identifier_jsonpaths.get(df_schema, []),
                bundle,
            )
        )
        for jsonpath in datafile_schema_resource_ref_jsonpaths.get(df_schema, []):
            for resource_usage in jsonpath.find(df):
                resource = bundle.resources.get(resource_usage.value)
                if resource:
                    resource["backrefs"].append({
                        "path": df_path,
                        "datafileSchema": df_schema,
                        "type": bundle.get_graphql_type_for_schema(df_schema).type,
                        "jsonpath": str(resource_usage.full_path),
                    })
                else:
                    errors.append(f"resource file {resource_usage.value} not found")
    return errors


def process_data_file_schema_object(
    datafile_schema: str,
    schema_object: dict[str, Any],
    graphql_type: GraphqlType,
    ctx: Context,
) -> list[str]:
    if datafile_schema in ctx.datafile_schema_resource_ref_paths:
        # shortcut if result has been calculated already
        return (
            ctx.datafile_schema_resource_ref_paths[datafile_schema],
            ctx.datafile_object_identifier_paths[datafile_schema],
            [],
        )
    elif datafile_schema in ctx.schema_path:
        # loop prevention
        return [], {}, []
    else:
        (
            resource_ref_paths,
            object_identifiers,
            unique_identifiers,
        ) = _find_resource_field_paths(
            datafile_schema, schema_object, graphql_type, ctx
        )
        # fill result cache
        ctx.datafile_schema_resource_ref_paths[datafile_schema] = resource_ref_paths
        ctx.datafile_object_identifier_paths[datafile_schema] = dict(object_identifiers)
        return resource_ref_paths, object_identifiers, unique_identifiers


def _find_resource_field_paths(
    datafile_schema: str,
    schema_object: dict[str, Any],
    graphql_type: GraphqlType,
    ctx: Context,
) -> list[str]:
    """
    inspecting a property of a datafile schema (and corresponding graphql type) to
    find all paths to resourcerefs

    * the trivial case is the property being a `resourceref` itself
    * if the property is a simple nested structure, we call this function again with the
      nested structure to recursively find all `resourcerefs` that might be inside
    * if the property can be of multiple types defined by jsonschemas `oneOf`, each
      subtype is inspected individually. in this case the corresponding graphql type
      is required to learn about the field name and type used to distinguish types
      from each other (e.g. `provider`). this information is then used to build
      proper jsonpaths to the respective `resourceref` fields
    """
    resource_paths = []
    object_identifier_paths = {}
    unique_properties = []
    for property_name, property in schema_object.get("properties", {}).items():
        property_gql_field = (
            graphql_type.fields_by_name.get(property_name, {}) if graphql_type else {}
        )
        property_graphql_type = (
            graphql_type.get_referenced_field_type(property_name)
            if graphql_type
            else None
        )
        (
            is_array,
            property_schema_name,
            property_schema_object,
        ) = _resolve_property_schema(property, ctx.bundle.schemas)
        if not property_schema_name and property_graphql_type:
            property_schema_name = property_graphql_type.spec.get("datafile")
            if property_schema_name:
                property_schema_object = ctx.bundle.schemas.get(property_schema_name)
        if not property_schema_object and property_schema_name:
            property_schema_object = ctx.bundle.schemas.get(property_schema_name)
        if property_gql_field.get("isContextUnique", False) or property_gql_field.get(
            "isUnique", False
        ):
            unique_properties.append(property_name)
        if property_schema_name == RESOURCE_REF:
            if is_array:
                resource_paths.append(f"{property_name}[*]")
            else:
                resource_paths.append(property_name)
        elif property_schema_object:
            interfaceResolverField = (
                property_graphql_type.get_interface_resolver_field()
                if property_graphql_type
                else None
            )
            if interfaceResolverField and "oneOf" in property_schema_object:
                for sub_schema_object in property_schema_object.get("oneOf"):
                    if "properties" not in sub_schema_object:
                        # sub type is a ref - resolve it
                        _, _, sub_schema_object = _resolve_property_schema(  # noqa: PLW2901
                            sub_schema_object, ctx.bundle.schemas
                        )
                    if not sub_schema_object:
                        continue
                    for sub_schema_discriminator in sub_schema_object["properties"][
                        interfaceResolverField
                    ]["enum"]:
                        property_graphql_sub_type = property_graphql_type.get_sub_type(
                            sub_schema_discriminator
                        )
                        (
                            sub_schema_resource_paths,
                            sub_object_identifiers,
                            sub_unique_properties,
                        ) = _find_resource_field_paths(
                            property_schema_name,
                            sub_schema_object,
                            property_graphql_sub_type,
                            ctx,
                        )
                        for p in sub_schema_resource_paths:
                            resource_paths.append(
                                f"{property_name}[?(@.{interfaceResolverField}"
                                f"=="
                                f"'{sub_schema_discriminator}')].{p}"
                            )
                        if sub_unique_properties:
                            object_identifier_paths[
                                f"{property_name}[?(@.{interfaceResolverField}"
                                f"=="
                                f"'{sub_schema_discriminator}')]"
                            ] = (
                                sub_unique_properties,
                                [
                                    (parse(path), properties)
                                    for path, properties in sub_object_identifiers.items()
                                ],
                            )
                            property_schema_object["properties"]["__identifier"] = {
                                "type": "string"
                            }
            elif not ctx.bundle.is_top_level_schema(property_schema_name):
                with ctx.step_into(datafile_schema):
                    property_graphql_type = (
                        graphql_type.get_referenced_field_type(property_name)
                        if graphql_type
                        else None
                    )
                    if property_schema_name:
                        resolver_func = process_data_file_schema_object
                    else:
                        resolver_func = _find_resource_field_paths
                    (
                        property_resource_paths,
                        property_object_identifiers,
                        property_unique_properties,
                    ) = resolver_func(
                        property_schema_name,
                        property_schema_object,
                        property_graphql_type,
                        ctx,
                    )
                    property_name_jsonpath = property_name
                    if is_array:
                        property_name_jsonpath = f"{property_name}[*]"
                    for p in property_resource_paths:
                        resource_paths.append(f"{property_name_jsonpath}.{p}")
                    if property_unique_properties:
                        object_identifier_paths[property_name_jsonpath] = (
                            property_unique_properties,
                            [
                                (parse(path), properties)
                                for path, properties in property_object_identifiers.items()
                            ],
                        )
                        property_schema_object["properties"]["__identifier"] = {
                            "type": "string"
                        }
    if unique_properties:
        schema_object["properties"]["__identifier"] = {"type": "string"}
    return resource_paths, object_identifier_paths, unique_properties


def _resolve_property_schema(property, schemas) -> tuple[bool, str | None, dict | None]:
    """
    this is a helper function to get the schema definition of a property, transparently
    dealing with refs and schema refs.
    """
    type = property.get("type")
    if type == "array":
        _, datafile_type, schema_object = _resolve_property_schema(
            property.get("items", {}), schemas
        )
        return True, datafile_type, schema_object
    elif type == "object":
        return False, None, property
    elif "oneOf" in property:
        return False, None, property
    else:
        ref = property.get("$ref")
        schema_ref = property.get("$schemaRef")
        if schema_ref:
            if isinstance(schema_ref, str) and schema_ref in schemas:
                return False, schema_ref, schemas[schema_ref]
            elif isinstance(schema_ref, dict):
                return (
                    False,
                    schema_ref["properties"].get("$schema", {}).get("enum")[0],
                    schema_ref,
                )
        if ref:
            return False, ref, schemas.get(ref)
        else:
            return False, None, None
