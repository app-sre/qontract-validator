from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Self

from validator.bundle import Bundle, GraphqlField, GraphqlTypeV2
from validator.jsonpath import JSONPath, JSONPathField, JSONPathIndex


@dataclass(frozen=True)
class Node:
    bundle: Bundle
    data: Any
    file_schema_path: str | None
    graphql_field_name: str | None
    graphql_type_name: str | None
    jsonpaths: list[JSONPath]
    path: str
    schema: Any
    schema_path: str | None
    parent: Self | None

    @property
    def graphql_type(self) -> GraphqlTypeV2 | None:
        if self.graphql_type_name:
            return self.bundle.graphql_lookup.get_by_type_name(self.graphql_type_name)
        return None

    @property
    def graphql_field(self) -> GraphqlField | None:
        if self.graphql_field_name is None:
            return None
        if graphql_type := self.graphql_type:
            return graphql_type.get_field(self.graphql_field_name)
        return None


def traverse_data(bundle: Bundle) -> Iterator[Node]:
    """
    Traverse the data files in the bundle and yield nodes representing each data item.

    Each node contains information about the data, its schema, GraphQL type, and JSON paths.

    Args:
        bundle (Bundle): The bundle containing data files and schemas.
    Yields:
        Node: A node representing a data item, including its data, schema, GraphQL type
    """
    for datafile_path, datafile in bundle.data.items():
        datafile_schema = datafile.get("$schema")
        schema = bundle.schemas.get(datafile_schema, {}) if datafile_schema else None
        graphql_type_name = (
            graphql_type.name
            if (
                datafile_schema
                and (
                    graphql_type := bundle.graphql_lookup.get_by_schema(datafile_schema)
                )
            )
            else None
        )
        node = Node(
            bundle=bundle,
            data=datafile,
            file_schema_path=datafile_schema,
            graphql_field_name=None,
            graphql_type_name=graphql_type_name,
            jsonpaths=[],
            path=datafile_path,
            schema=schema,
            schema_path=datafile_schema,
            parent=None,
        )
        yield from _traverse_node(node)


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


def _next_dict_node(node: Node, key: str, value: Any) -> Node | None:
    if key == "$schema":
        return None
    graphql_type, graphql_field = _next_dict_graphql(node, key)
    schema = _next_dict_schema(node, key)
    return _next_node(
        node=node,
        schema=schema,
        data=value,
        jsonpaths=[*node.jsonpaths, JSONPathField(key)],
        graphql_type=graphql_type,
        graphql_field=graphql_field,
    )


def _next_list_node(node: Node, index: int, value: Any) -> Node:
    schema = node.schema.get("items") if node.schema else None
    return _next_node(
        node=node,
        schema=schema,
        data=value,
        jsonpaths=[*node.jsonpaths, JSONPathIndex(index)],
        graphql_type=node.graphql_type,
        graphql_field=node.graphql_field,
    )


def _next_dict_graphql(
    node: Node,
    field_name: str,
) -> tuple[GraphqlTypeV2 | None, GraphqlField | None]:
    """
    Resolve the next GraphQL type and field for a given dict node and field name.

    For crossref fields (field name is "$ref"), it skips the resolution.
    If current node has no graphql field yet, pick the field from the current type.
    If current node graphql field is pointing to another type, resolve the new type and field.

    Args:
        node (Node): The current node containing the GraphQL type and field information.
        field_name (str): The name of the next field.
    Returns:
        tuple[GraphqlTypeV2 | None, GraphqlField | None]: A tuple containing the resolved GraphQL type and field.
    """
    graphql_type = node.graphql_type
    if graphql_type is None:
        return None, None
    graphql_field = node.graphql_field

    if field_name == "$ref":
        return graphql_type, graphql_field

    if graphql_field is None:
        return graphql_type, graphql_type.get_field(field_name)

    if (new_graphql_type_name := graphql_field.get("type")) and (
        new_graphql_type := node.bundle.graphql_lookup.get_by_type_name(
            new_graphql_type_name
        )
    ):
        return new_graphql_type, new_graphql_type.get_field(field_name)
    return None, None


def _next_dict_schema(
    node: Node,
    key: str,
) -> Any:
    """
    Resolve the next schema for a given dict node and key.

    If the schema is a crossref (contains "$schemaRef"), it skips the resolution.

    Args:
        node (Node): The current node containing the schema information.
        key (str): The key to next schema.
    Returns:
        Any: The resolved schema for the given key, or None if not found.
    """
    if schema := node.schema:
        if isinstance(schema, dict) and "$schemaRef" in schema:
            # skip resolve crossref fields
            return schema
        return schema.get("properties", {}).get(key)
    return None


def _next_node(
    node: Node,
    schema: Any,
    data: Any,
    jsonpaths: list[JSONPath],
    graphql_type: GraphqlTypeV2 | None = None,
    graphql_field: GraphqlField | None = None,
) -> Node:
    """
    Create a new Node based on the current node info.

    This function resolves the schema and GraphQL type for the new node based on the current node's schema and data.
    If the GraphQL type is an interface, it resolves the interface type name based on the data.

    Args:
        node (Node): The current node containing the data, schema, and GraphQL type information
        schema (Any): The schema for the new node.
        data (Any): The data for the new node.
        jsonpaths (list[JSONPath]): The JSON paths for the new node.
        graphql_type (GraphqlTypeV2 | None): The GraphQL type for the new
        graphql_field (GraphqlField | None): The GraphQL field for the new node.
    Returns:
        Node: A new Node instance with the updated data, schema, and GraphQL type information.
    """
    graphql_field_type = (
        node.bundle.graphql_lookup.get_by_type_name(graphql_field["type"])
        if graphql_field
        else None
    )
    new_schema_path, new_schema = _resolve_schema(
        schema_path=node.schema_path,
        schema=schema,
        bundle=node.bundle,
        data=data,
        graphql_type=graphql_field_type,
    )
    if resolved_graphql_type := _resolve_graphql_interface_type(
        graphql_field_type, node.bundle, data
    ):
        return Node(
            bundle=node.bundle,
            data=data,
            file_schema_path=node.file_schema_path,
            graphql_field_name=None,
            graphql_type_name=resolved_graphql_type.name,
            jsonpaths=jsonpaths,
            path=node.path,
            schema=new_schema,
            schema_path=new_schema_path,
            parent=node,
        )

    graphql_type_name = graphql_type.name if graphql_type else None
    graphql_field_name = graphql_field.get("name") if graphql_field else None
    return Node(
        bundle=node.bundle,
        data=data,
        file_schema_path=node.file_schema_path,
        graphql_field_name=graphql_field_name,
        graphql_type_name=graphql_type_name,
        jsonpaths=jsonpaths,
        path=node.path,
        schema=new_schema,
        schema_path=new_schema_path,
        parent=node,
    )


def _resolve_graphql_interface_type(
    graphql_type: GraphqlTypeV2 | None,
    bundle: Bundle,
    data: Any,
) -> GraphqlTypeV2 | None:
    """
    Resolve the GraphQL interface type based on the data.

    If the GraphQL type is an interface, it resolves the interface type name using the data.
    Only resolve if the GraphQL field is an interface with fieldMap strategy.

    Args:
        graphql_type (GraphqlTypeV2 | None): The GraphQL type to resolve.
        bundle (Bundle): The bundle containing the GraphQL types.
        data (Any): The data to resolve the interface type name.
    Returns:
        GraphqlTypeV2 | None: The resolved GraphQL type if it is an interface, otherwise None.
    """
    if graphql_type is None or not graphql_type.is_interface:
        return None
    if name := graphql_type.resolve_interface_type_name(data):
        return bundle.graphql_lookup.get_by_type_name(name)
    return None


def _resolve_schema(
    schema_path: str | None,
    schema: Any,
    bundle: Bundle,
    data: Any,
    graphql_type: GraphqlTypeV2 | None,
) -> tuple[str | None, Any]:
    """
    Resolve the schema based on the schema path, schema, bundle, data, and GraphQL type.

    If the schema is a reference ($ref), it resolves the schema from the bundle.
    If the schema has a oneOf condition and the GraphQL type is provided, it finds the appropriate schema based on the field and value.

    Args:
        schema_path (str | None): The path to the schema.
        schema (Any): The schema to resolve.
        bundle (Bundle): The bundle containing the schemas.
        data (Any): The data to resolve the schema against.
        graphql_type (GraphqlTypeV2 | None): The GraphQL type to resolve the schema against.
    Returns:
        tuple[str | None, Any]: A tuple containing the resolved schema path and schema.
    """
    if (
        schema_path is None
        or schema is None
        or not isinstance(schema, dict)
        or "$schemaRef" in schema
        or not isinstance(data, dict)
    ):
        return schema_path, schema
    if ref := schema.get("$ref"):
        return _resolve_schema(
            schema_path=ref,
            schema=bundle.schemas.get(ref),
            bundle=bundle,
            data=data,
            graphql_type=graphql_type,
        )
    if (
        (schemas := schema.get("oneOf"))
        and graphql_type
        and (field := graphql_type.interface_resolve_field_name())
        and (field_value := graphql_type.resolve_interface_field_value(data))
    ):
        new_schema = _find_one_of_schema(schemas, field, field_value)
        return schema_path, new_schema
    return schema_path, schema


def _find_one_of_schema(
    schemas: list[dict[str, Any]],
    field: str,
    field_value: Any,
) -> Any:
    for schema in schemas:
        if field_value in schema.get("properties", {}).get(field, {}).get("enum", []):
            return schema
    return None
