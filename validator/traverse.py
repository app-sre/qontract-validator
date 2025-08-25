from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, NamedTuple, Self

from validator.bundle import RESOURCE_REF, Bundle, GraphqlField, GraphqlTypeV2
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
    schema_one_of_root: Any
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

    def is_resource_ref(self) -> bool:
        return (
            self.schema is not None
            and isinstance(self.schema, dict)
            and self.schema.get("$ref") == RESOURCE_REF
        )

    def resolve_ref(self) -> dict[str, Any] | None:
        if self.data and isinstance(self.data, str):
            return self.bundle.data.get(self.data)
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
            schema_one_of_root=None,
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


class GraphqlInfo(NamedTuple):
    graphql_type: GraphqlTypeV2 | None
    graphql_field: GraphqlField | None


class SchemaInfo(NamedTuple):
    schema_path: str | None
    schema: Any
    schema_one_of_root: Any


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
) -> GraphqlInfo:
    """
    Resolve the next GraphQL type and field for a given dict node and field name.

    For crossref fields (field name is "$ref"), it skips the resolution.
    If current node has no graphql field yet, pick the field from the current type.
    If current node graphql field is pointing to another type, resolve the new type and field.

    Args:
        node (Node): The current node containing the GraphQL type and field information.
        field_name (str): The name of the next field.
    Returns:
        GraphqlInfo: A tuple containing the resolved GraphQL type and field.
    """
    graphql_type = node.graphql_type
    if graphql_type is None:
        return GraphqlInfo(None, None)
    graphql_field = node.graphql_field

    if field_name == "$ref":
        return GraphqlInfo(graphql_type, graphql_field)

    if graphql_field is None:
        return GraphqlInfo(graphql_type, graphql_type.get_field(field_name))

    if (new_graphql_type_name := graphql_field.get("type")) and (
        new_graphql_type := node.bundle.graphql_lookup.get_by_type_name(
            new_graphql_type_name
        )
    ):
        return GraphqlInfo(new_graphql_type, new_graphql_type.get_field(field_name))
    return GraphqlInfo(None, None)


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
    schema_info = _resolve_schema(
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
            schema=schema_info.schema,
            schema_one_of_root=schema_info.schema_one_of_root,
            schema_path=schema_info.schema_path,
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
        schema=schema_info.schema,
        schema_one_of_root=schema_info.schema_one_of_root,
        schema_path=schema_info.schema_path,
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
) -> SchemaInfo:
    """
    Resolve the schema based on the schema path, schema, bundle, data, and GraphQL type.

    If the schema is a reference ($ref), it resolves the schema from the bundle.
    If the schema has a oneOf condition, it will pick the appropriate schema based on:
    * inline and referenced schema
    * graphql field and value for fieldMap strategy

    Args:
        schema_path (str | None): The path to the schema.
        schema (Any): The schema to resolve.
        bundle (Bundle): The bundle containing the schemas.
        data (Any): The data to resolve the schema against.
        graphql_type (GraphqlTypeV2 | None): The GraphQL type to resolve the schema against.
    Returns:
    """
    schema_info = _resolve_ref_schema(
        schema_info=SchemaInfo(
            schema_path=schema_path,
            schema=schema,
            schema_one_of_root=None,
        ),
        bundle=bundle,
    )

    if (
        schema_info.schema_path
        and schema_info.schema
        and isinstance(schema_info.schema, dict)
        and "$schemaRef" not in schema_info.schema
        and (schemas := schema_info.schema.get("oneOf"))
    ):
        if _is_inline_and_referenced(schemas):
            new_schema = _find_one_of_schema_by_crossref_data(schemas, data)
            return _resolve_ref_schema(
                SchemaInfo(
                    schema_path=schema_info.schema_path,
                    schema=new_schema,
                    schema_one_of_root=schema_info.schema_one_of_root,
                ),
                bundle=bundle,
            )
        if (
            graphql_type
            and (field := graphql_type.interface_resolve_field_name())
            and (field_value := graphql_type.resolve_interface_field_value(data))
        ):
            return _find_one_of_schema_by_enum(
                root_schema_info=schema_info,
                schemas=schemas,
                field=field,
                field_value=field_value,
                bundle=bundle,
            )
    return schema_info


def _resolve_ref_schema(
    schema_info: SchemaInfo,
    bundle: Bundle,
) -> SchemaInfo:
    if (
        (schema := schema_info.schema)
        and isinstance(schema, dict)
        and "$schemaRef" not in schema
        and (ref := schema.get("$ref"))
        and (new_schema := bundle.schemas.get(ref))
    ):
        return SchemaInfo(
            schema_path=ref,
            schema=new_schema,
            schema_one_of_root=None,
        )
    return schema_info


def _find_one_of_schema_by_enum(
    root_schema_info: SchemaInfo,
    schemas: list[Any],
    field: str,
    field_value: Any,
    bundle: Bundle,
) -> SchemaInfo:
    for schema in schemas:
        schema_info = _resolve_ref_schema(
            SchemaInfo(
                schema_path=root_schema_info.schema_path,
                schema=schema,
                schema_one_of_root=None,
            ),
            bundle=bundle,
        )
        if (
            schema_info.schema
            and isinstance(schema_info.schema, dict)
            and field_value
            in schema_info.schema.get("properties", {}).get(field, {}).get("enum", [])
        ):
            return SchemaInfo(
                schema_path=schema_info.schema_path,
                schema=schema_info.schema,
                schema_one_of_root=root_schema_info.schema,
            )
    return SchemaInfo(
        schema_path=root_schema_info.schema_path,
        schema=None,
        schema_one_of_root=None,
    )


def _find_one_of_schema_by_crossref_data(
    schemas: list[dict[str, Any]],
    data: Any,
) -> Any:
    if isinstance(data, dict) and "$ref" in data:
        return next(schema for schema in schemas if "$schemaRef" in schema)
    return next(schema for schema in schemas if "$schemaRef" not in schema)


def _is_inline_and_referenced(schemas: list[dict[str, Any]]) -> bool:
    """
    Check if the schemas are inline and referenced.

    example:
    ```yaml
    oneOf:
      # inline
      - "$ref": "another-schema-1.yml"
      # referenced
      - "$ref": "/common-1.json#/definitions/crossref"
        "$schemaRef": "another-schema-1.yml"
    ```

    Args:
        schemas (list): The list of schemas to check.
    Returns:
        bool: True if the schemas are inline and referenced, otherwise False.
    """
    inline_count = sum("$schemaRef" not in schema for schema in schemas)
    referenced_count = sum("$schemaRef" in schema for schema in schemas)
    return inline_count == 1 and referenced_count == 1
