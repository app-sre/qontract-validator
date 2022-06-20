import sys
from contextlib import contextmanager
from typing import Any, Optional, Tuple
from jsonpath_ng.ext import parse

from validator.bundle import Bundle, GraphqlType


RESOURCE_REF = "/common-1.json#/definitions/resourceref"
CROSS_REF = "/common-1.json#/definitions/crossref"


class SchemaTraversalLoopException(Exception):
    pass


class Context:
    def __init__(self, bundle: Bundle):
        self.bundle = bundle
        self.datafile_schema_resource_ref_paths: dict[str, list[str]] = {}
        self.schema_path: list[str] = []

    @contextmanager
    def step_into(self, datafile_schema: str):
        try:
            self.schema_path.append(datafile_schema)
            yield
        finally:
            self.schema_path.pop()


def resolve_resource_references(bundle: Bundle):

    # build up a list of resource references on a type level
    context = Context(bundle)

    # find all jsonpath to resource reference fields in the schemas
    datafile_schema_resource_ref_jsonpaths: dict[str, list] = {}
    for datafile_schema, schema_object in bundle.schemas.items():
        if bundle.is_top_level_schema(datafile_schema):
            graphql_type = bundle.get_graphql_type_for_schema(datafile_schema)
            paths = process_data_file_schema_object(
                datafile_schema, schema_object, graphql_type, context
            )
            datafile_schema_resource_ref_jsonpaths[datafile_schema] = [
                parse(p) for p in paths
            ]

    # use the jsonpaths to find actual resources and backref them to their data files
    for df_path, df in bundle.data.items():
        df_schema = df["$schema"]
        for jsonpath in datafile_schema_resource_ref_jsonpaths.get(df_schema, []):
            for resource_usage in jsonpath.find(df):
                resource = bundle.resources.get(resource_usage.value)
                if resource:
                    resource["backrefs"].append(
                        {
                            "path": df_path,
                            "datafileSchema": df_schema,
                            "type": bundle.get_graphql_type_for_schema(df_schema).type,
                            "jsonpath": str(resource_usage.full_path),
                        }
                    )
                else:
                    print(f"resource {resource_usage.value} not found", file=sys.stderr)
                    exit(1)


def process_data_file_schema_object(
    datafile_schema: str,
    schema_object: dict[str, Any],
    graphql_type: GraphqlType,
    ctx: Context,
) -> list[str]:
    if datafile_schema in ctx.datafile_schema_resource_ref_paths:
        # shortcut if result has been calculated already
        return ctx.datafile_schema_resource_ref_paths[datafile_schema]
    elif datafile_schema in ctx.schema_path:
        # loop prevention
        return []
    else:
        paths = _find_resource_field_paths(
            datafile_schema, schema_object, graphql_type, ctx
        )
        # fill result cache
        ctx.datafile_schema_resource_ref_paths[datafile_schema] = paths
        return paths


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
    paths = []
    for property_name, property in schema_object.get("properties", {}).items():
        (
            is_array,
            property_schema_name,
            property_schema_object,
        ) = _resolve_property_schema(property, ctx.bundle.schemas)
        if property_schema_name == RESOURCE_REF:
            # todo check if this can be in a list too?
            paths.append(property_name)
        elif property_schema_object:
            property_graphql_type = (
                graphql_type.get_referenced_field_type(property_name)
                if graphql_type
                else None
            )
            interfaceResolverField = (
                property_graphql_type.get_interface_resolver_field()
                if property_graphql_type
                else None
            )
            if interfaceResolverField and "oneOf" in property_schema_object:
                for sub_schema_object in property_schema_object.get("oneOf"):
                    if "properties" not in sub_schema_object:
                        # sub type is a ref - resolve it
                        _, _, sub_schema_object = _resolve_property_schema(
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
                        sub_schema_paths = _find_resource_field_paths(
                            property_schema_name,
                            sub_schema_object,
                            property_graphql_sub_type,
                            ctx,
                        )
                        for p in sub_schema_paths:
                            paths.append(
                                f"{property_name}[?(@.{interfaceResolverField}"
                                f"=="
                                f"'{sub_schema_discriminator}')].{p}"
                            )
            else:
                if not ctx.bundle.is_top_level_schema(property_schema_name):
                    with ctx.step_into(datafile_schema):
                        property_graphql_type = (
                            graphql_type.get_referenced_field_type(property_name)
                            if graphql_type
                            else None
                        )
                        for p in process_data_file_schema_object(
                            property_schema_name,
                            property_schema_object,
                            property_graphql_type,
                            ctx,
                        ):
                            if is_array:
                                paths.append(f"{property_name}[*].{p}")
                            else:
                                paths.append(f"{property_name}.{p}")
    return paths


def _resolve_property_schema(
    property, schemas
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    this is a helper function to get the schema definition of a property, transparently
    dealing with refs and schema refs.
    """
    type = property.get("type")
    if type == "array":
        _, datafile_type, schema_object = _resolve_property_schema(
            property.get("items"), schemas
        )
        return True, datafile_type, schema_object
    elif type == "object":
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
