import hashlib
from collections import defaultdict
from collections.abc import Hashable
from dataclasses import dataclass
from typing import Any, TypedDict

from validator.bundle import Bundle, GraphqlField
from validator.jsonpath import (
    JSONPath,
    JSONPathField,
    JSONPathIndex,
    build_jsonpath,
)
from validator.traverse import traverse_data

RESOURCE_REF_SCHEMA = {
    "$ref": "/common-1.json#/definitions/resourceref",
}


class Backref(TypedDict):
    path: str
    datafileSchema: str
    type: str
    jsonpath: str


@dataclass
class UniqueFieldNode:
    schema: dict[str, Any]
    data: dict[str, Any]
    props: list[str]


def postprocess_bundle(
    bundle: Bundle,
    checksum_field_name: str | None = None,
) -> None:
    if checksum_field_name:
        patch_schema_checksum_field(bundle, checksum_field_name)

    unique_field_nodes: dict[tuple[str, str], UniqueFieldNode] = {}
    backrefs_by_resource_path = defaultdict(list)
    for node in traverse_data(bundle):
        if node.schema == RESOURCE_REF_SCHEMA and node.data and node.file_schema_path:
            # TODO: type is not needed, remove it in the next version
            # this logic just keep the type for backward compatibility
            type_name = (
                graphql_type.name
                if (
                    graphql_type := bundle.graphql_lookup.get_by_schema(
                        node.file_schema_path
                    )
                )
                else ""
            )
            backrefs_by_resource_path[node.data].append(
                Backref(
                    path=node.path,
                    datafileSchema=node.file_schema_path,
                    type=type_name,
                    jsonpath=build_jsonpath(node.jsonpaths),
                )
            )
        if (
            (graphql_field := node.graphql_field)
            and _is_unique_field(graphql_field)
            and node.parent
            and isinstance(node.parent.data, dict)
            and (prop := _extract_array_item_property(node.jsonpaths))
        ):
            key = (node.path, build_jsonpath(node.jsonpaths[:-1]))
            if unique_node := unique_field_nodes.get(key):
                unique_node.props.append(prop)
            else:
                unique_field_nodes[key] = UniqueFieldNode(
                    schema=node.parent.schema,
                    data=node.parent.data,
                    props=[prop],
                )

    for resource_path, resource in bundle.resources.items():
        resource["backrefs"] = backrefs_by_resource_path.get(resource_path, [])

    for unique_field_node in unique_field_nodes.values():
        unique_field_node.schema["properties"]["__identifier"] = {
            "type": "string",
        }
        unique_field_node.data["__identifier"] = _compute_identifier(
            unique_field_node.props, unique_field_node.data
        )


def patch_schema_checksum_field(
    bundle: Bundle,
    checksum_field_name: str,
) -> None:
    for s in bundle.schemas.values():
        if s["$schema"] == "/metaschema-1.json":
            s["properties"][checksum_field_name] = {
                "type": "string",
                "description": "sha256sum of the datafile",
            }


def _is_unique_field(graphql_field: GraphqlField) -> bool:
    """Check if the field is unique or context unique."""
    return any(graphql_field.get(field) for field in ["isUnique", "isContextUnique"])


def _extract_array_item_property(jsonpaths: list[JSONPath]) -> str | None:
    if len(jsonpaths) < 2:
        return None
    if not isinstance(jsonpaths[-2], JSONPathIndex):
        return None
    property_path = jsonpaths[-1]
    if isinstance(property_path, JSONPathField):
        return property_path.field
    return None


# TODO: this is for backward compatibility, use sha256sum on json string in the next version
def _compute_identifier(properties: list[str], obj: dict[str, Any]) -> str | None:
    def to_hashable(field):
        if isinstance(field, Hashable):
            return field
        return repr(field)

    obj_id = [to_hashable(obj.get(item)) for item in properties]
    if all(i is None for i in obj_id):
        return None
    hash_id = hashlib.md5()  # noqa: S324
    for i in obj_id:
        hash_id.update(str(i).encode())
    return hash_id.hexdigest()
