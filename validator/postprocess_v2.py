import hashlib
from collections import defaultdict
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from typing import Any, TypedDict

from validator.bundle import Bundle, GraphqlField
from validator.jsonpath import (
    JSONPathField,
    JSONPathIndex,
    build_jsonpath,
)
from validator.traverse import Node, traverse_data

CHECKSUM_FIELD_SCHEMA = {
    "type": "string",
    "description": "sha256sum of the datafile",
}
IDENTIFIER_FIELD_NAME = "__identifier"
IDENTIFIER_SCHEMA = {
    IDENTIFIER_FIELD_NAME: {
        "type": "string",
    }
}
RESOURCE_REF = "/common-1.json#/definitions/resourceref"


class Backref(TypedDict):
    path: str
    datafileSchema: str
    type: str
    jsonpath: str


@dataclass
class ContextUniqueNode:
    schema: dict[str, Any]
    schema_one_of_root: Any
    data: dict[str, Any]
    props: set[str]
    path: str
    jsonpath: str

    @property
    def identifier(self) -> str | None:
        return _compute_identifier(self.props, self.data)


def postprocess_bundle(
    bundle: Bundle,
    checksum_field_name: str | None = None,
) -> None:
    if checksum_field_name:
        patch_schema_checksum_field(bundle, checksum_field_name)

    backrefs_by_resource_path = defaultdict(list)
    context_unique_nodes: dict[tuple[str, str], ContextUniqueNode] = {}

    for node in traverse_data(bundle):
        if backref := build_backref(node):
            backrefs_by_resource_path[node.data].append(backref)

        if context_unique_node := build_context_unique_node(node):
            key = (context_unique_node.path, context_unique_node.jsonpath)
            if existing_node := context_unique_nodes.get(key):
                existing_node.props.update(context_unique_node.props)
            else:
                context_unique_nodes[key] = context_unique_node

    for resource_path, resource in bundle.resources.items():
        resource["backrefs"] = backrefs_by_resource_path.get(resource_path, [])

    for context_unique_node in context_unique_nodes.values():
        patch_context_unique_schema_and_data(context_unique_node)


def patch_context_unique_schema_and_data(
    context_unique_node: ContextUniqueNode,
) -> None:
    if not context_unique_node.identifier:
        return
    context_unique_node.schema["properties"].update(IDENTIFIER_SCHEMA)
    if (one_of_root := context_unique_node.schema_one_of_root) and isinstance(
        one_of_root, dict
    ):
        if "properties" not in one_of_root:
            one_of_root["properties"] = IDENTIFIER_SCHEMA
        else:
            one_of_root["properties"].update(IDENTIFIER_SCHEMA)
    context_unique_node.data[IDENTIFIER_FIELD_NAME] = context_unique_node.identifier


def patch_schema_checksum_field(
    bundle: Bundle,
    checksum_field_name: str,
) -> None:
    for s in bundle.schemas.values():
        if s["$schema"] == "/metaschema-1.json":
            s["properties"][checksum_field_name] = CHECKSUM_FIELD_SCHEMA


def build_backref(node: Node) -> Backref | None:
    """
    Build a back reference for a resource reference node.

    This function checks if the node is a resource reference by matching field schema
    $ref is "/common-1.json#/definitions/resourceref".

    Args:
        node (Node): The node to check for a back reference.
    Returns:
        Backref | None: Returns a Backref object if the node is a resource reference,
    """
    if (
        (schema := node.schema)
        and isinstance(schema, dict)
        and schema.get("$ref") == RESOURCE_REF
        and node.data
        and node.file_schema_path
    ):
        # TODO: type is not needed, remove it in the next version  # noqa: FIX002, TD002, TD003
        # this logic just keep the type for backward compatibility
        type_name = (
            graphql_type.name
            if (
                graphql_type := node.bundle.graphql_lookup.get_by_schema(
                    node.file_schema_path
                )
            )
            else ""
        )
        return Backref(
            path=node.path,
            datafileSchema=node.file_schema_path,
            type=type_name,
            jsonpath=build_jsonpath(node.jsonpaths),
        )
    return None


def build_context_unique_node(node: Node) -> ContextUniqueNode | None:
    """
    Build a context unique node for a given node.

    If the current traversed node is directly inside an array item,
    and current graphql field has isUnique or isContextUnique set to true,
    then a UniqueFieldNode is created.
    For crossref field ($ref), it will try to find all unique fields from target file top level graphql type fields.
    Non-top level graphql type fields are covered by non crossref field.

    Args:
        node (Node): The node to check for a context unique field.
    Returns:
        ContextUniqueNode | None: Returns a ContextUniqueNode if the node is a unique field, otherwise None.
    """
    match node.jsonpaths:
        case [*_, JSONPathIndex(), JSONPathField(field)]:
            return (
                _build_crossref_unique_field_node(node)
                if field == "$ref"
                else _build_array_item_unique_field_node(node, field)
            )
        case _:
            return None


def _build_crossref_unique_field_node(node: Node) -> ContextUniqueNode | None:
    path = node.data
    if (
        path
        and (data := node.bundle.data.get(path))
        and (schema_path := data.get("$schema"))
        and (graphql_type := node.bundle.graphql_lookup.get_by_schema(schema_path))
        and (schema := node.bundle.schemas.get(schema_path))
    ):
        props = {
            prop
            for prop, field in graphql_type.fields.items()
            if _is_context_unique_field(field)
        }
        if props:
            return ContextUniqueNode(
                schema=schema,
                schema_one_of_root=None,
                data=data,
                props=props,
                path=path,
                jsonpath="",
            )
    return None


def _build_array_item_unique_field_node(
    node: Node,
    field: str,
) -> ContextUniqueNode | None:
    if (
        node.parent
        and isinstance(node.parent.data, dict)
        and (graphql_field := node.graphql_field)
        and _is_context_unique_field(graphql_field)
    ):
        return ContextUniqueNode(
            schema=node.parent.schema,
            schema_one_of_root=node.parent.schema_one_of_root,
            data=node.parent.data,
            props={field},
            path=node.path,
            jsonpath=build_jsonpath(node.jsonpaths[:-1]),
        )
    return None


def _is_context_unique_field(graphql_field: GraphqlField) -> bool:
    """Check if the field is unique or context unique."""
    return any(graphql_field.get(field) for field in ["isUnique", "isContextUnique"])


# TODO: this is for backward compatibility, use sha256sum on json string in the next version  # noqa: FIX002, TD002, TD003
def _compute_identifier(properties: Iterable[str], obj: dict[str, Any]) -> str | None:
    def to_hashable(field):
        if isinstance(field, Hashable):
            return field
        return repr(field)

    obj_id = [to_hashable(obj.get(item)) for item in sorted(properties)]
    if all(i is None for i in obj_id):
        return None
    hash_id = hashlib.md5()  # noqa: S324
    for i in obj_id:
        hash_id.update(str(i).encode())
    return hash_id.hexdigest()
