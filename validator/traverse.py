from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from validator.bundle import Bundle, GraphqlField
from validator.jsonpath import JSONPath, JSONPathField, JSONPathIndex


@dataclass(frozen=True)
class Node:
    bundle: Bundle
    data: Any
    graphql_field_name: str | None
    graphql_name: str | None
    jsonpaths: list[JSONPath]
    path: str
    schema: Any
    schema_path: str | None

    @property
    def graphql_field(self) -> GraphqlField | None:
        if self.graphql_name is None or self.graphql_field_name is None:
            return None
        return self.bundle.graphql_lookup.get_field(
            self.graphql_name, self.graphql_field_name
        )


def _next_graphql_field(
    node: Node,
    field_name: str,
) -> tuple[str | None, GraphqlField | None]:
    if node.graphql_name is None:
        return None, None
    graphql_field = node.graphql_field
    # skip resolve for crossref fields
    if field_name == "$ref":
        return node.graphql_name, graphql_field
    if graphql_field is None:
        return node.graphql_name, node.bundle.graphql_lookup.get_field(
            node.graphql_name,
            field_name,
        )
    new_graphql_name = graphql_field.get("type")
    if new_graphql_name is None:
        return None, None
    return new_graphql_name, node.bundle.graphql_lookup.get_field(
        new_graphql_name,
        field_name,
    )


def _next_schema(
    node: Node,
    key: str,
) -> tuple[str | None, Any]:
    if node.schema_path is None or node.schema is None:
        return None, None
    # skip resolve crossref fields
    if "$schemaRef" in node.schema:
        return node.schema_path, node.schema
    if ref := node.schema.get("$ref"):
        new_schema_path = ref
        schema = node.bundle.schemas.get(ref)
    else:
        new_schema_path = node.schema_path
        schema = node.schema
    if schema is None:
        return None, None
    new_schema = schema.get("properties", {}).get(key)
    return new_schema_path, new_schema


def _next_dict_node(node: Node, key: str, value: Any) -> Node | None:
    if key == "$schema":
        return None
    graphql_name, graphql_field = _next_graphql_field(node, key)
    graphql_field_name = graphql_field.get("name") if graphql_field else None
    schema_path, schema = _next_schema(node, key)
    return Node(
        bundle=node.bundle,
        data=value,
        graphql_field_name=graphql_field_name,
        graphql_name=graphql_name,
        jsonpaths=node.jsonpaths + [JSONPathField(key)],
        path=node.path,
        schema=schema,
        schema_path=schema_path,
    )


def _next_list_node(node: Node, index: int, value: Any) -> Node:
    schema = node.schema.get("items") if node.schema_path and node.schema else None
    return Node(
        bundle=node.bundle,
        data=value,
        graphql_field_name=node.graphql_field_name,
        graphql_name=node.graphql_name,
        jsonpaths=node.jsonpaths + [JSONPathIndex(index)],
        path=node.path,
        schema=schema,
        schema_path=node.schema_path,
    )


def _traverse_node(node: Node) -> Iterator[Node]:
    if isinstance(node.data, dict):
        for key, value in node.data.items():
            if new_node := _next_dict_node(node, key, value):
                yield from _traverse_node(new_node)
    elif isinstance(node.data, list):
        for index, value in enumerate(node.data):
            new_node = _next_list_node(node, index, value)
            yield from _traverse_node(new_node)
        return
    else:
        yield node


def traverse_data(bundle: Bundle) -> Iterator[Node]:
    for datafile_path, datafile in bundle.data.items():
        datafile_schema = datafile.get("$schema")
        schema = bundle.schemas.get(datafile_schema, {})
        graphql_name = (
            bundle.graphql_lookup.get_name(datafile_schema) if datafile_schema else None
        )
        node = Node(
            bundle=bundle,
            data=datafile,
            graphql_field_name=None,
            graphql_name=graphql_name,
            jsonpaths=[],
            path=datafile_path,
            schema=schema,
            schema_path=datafile_schema,
        )
        yield from _traverse_node(node)
