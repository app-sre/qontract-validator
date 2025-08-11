from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from validator.bundle import Bundle, GraphqlField, GraphqlTypeV2
from validator.jsonpath import JSONPath, JSONPathField, JSONPathIndex


@dataclass(frozen=True)
class Node:
    bundle: Bundle
    data: Any
    graphql_field_name: str | None
    graphql_type_name: str | None
    jsonpaths: list[JSONPath]
    path: str
    schema: Any
    schema_path: str | None

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


def _next_dict_graphql(
    node: Node,
    field_name: str,
) -> tuple[GraphqlTypeV2 | None, GraphqlField | None]:
    graphql_type = node.graphql_type
    if graphql_type is None:
        return None, None
    graphql_field = node.graphql_field

    if field_name == "$ref":
        # skip resolve for crossref fields
        return graphql_type, graphql_field

    if graphql_field is None:
        # pick the field from the current type
        return graphql_type, graphql_type.get_field(field_name)

    # current field is pointing to another type
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
    if schema := node.schema:
        if isinstance(schema, dict) and "$schemaRef" in schema:
            # skip resolve crossref fields
            return schema
        return schema.get("properties", {}).get(key)
    return None


def _next_dict_node(node: Node, key: str, value: Any) -> Node | None:
    if key == "$schema":
        return None
    jsonpaths = [*node.jsonpaths, JSONPathField(key)]
    graphql_type, graphql_field = _next_dict_graphql(node, key)
    graphql_field_type = (
        node.bundle.graphql_lookup.get_by_type_name(graphql_field["type"])
        if graphql_field
        else None
    )
    schema = _next_dict_schema(node, key)
    new_schema_path, new_schema = _resolve_schema(
        node.schema_path, schema, node.bundle, value, graphql_field_type
    )
    if (
        graphql_field_type
        and graphql_field_type.is_interface
        and (
            resolved_graphql := _resolve_graphql_type(
                graphql_field_type, node.bundle, value
            )
        )
    ):
        return Node(
            bundle=node.bundle,
            data=value,
            graphql_field_name=None,
            graphql_type_name=resolved_graphql.name,
            jsonpaths=jsonpaths,
            path=node.path,
            schema=new_schema,
            schema_path=new_schema_path,
        )

    graphql_type_name = graphql_type.name if graphql_type else None
    graphql_field_name = graphql_field.get("name") if graphql_field else None
    return Node(
        bundle=node.bundle,
        data=value,
        graphql_field_name=graphql_field_name,
        graphql_type_name=graphql_type_name,
        jsonpaths=jsonpaths,
        path=node.path,
        schema=new_schema,
        schema_path=new_schema_path,
    )


def _next_list_node(node: Node, index: int, value: Any) -> Node:
    jsonpaths = [*node.jsonpaths, JSONPathIndex(index)]
    schema = node.schema.get("items") if node.schema_path and node.schema else None
    graphql_type = (
        node.bundle.graphql_lookup.get_by_type_name(graphql_field["type"])
        if (graphql_field := node.graphql_field)
        else None
    )
    new_schema_path, new_schema = _resolve_schema(
        node.schema_path, schema, node.bundle, value, graphql_type
    )
    if (
        graphql_type
        and graphql_type.is_interface
        and (
            resolved_graphql := _resolve_graphql_type(graphql_type, node.bundle, value)
        )
    ):
        return Node(
            bundle=node.bundle,
            data=value,
            graphql_field_name=None,
            graphql_type_name=resolved_graphql.name,
            jsonpaths=jsonpaths,
            path=node.path,
            schema=new_schema,
            schema_path=new_schema_path,
        )
    return Node(
        bundle=node.bundle,
        data=value,
        graphql_field_name=node.graphql_field_name,
        graphql_type_name=node.graphql_type_name,
        jsonpaths=[*node.jsonpaths, JSONPathIndex(index)],
        path=node.path,
        schema=new_schema,
        schema_path=new_schema_path,
    )


def _resolve_graphql_type(
    graphql_type: GraphqlTypeV2,
    bundle: Bundle,
    data: Any,
) -> GraphqlTypeV2 | None:
    if not graphql_type.is_interface or not graphql_type.interface_resolve:
        return graphql_type
    match graphql_type.interface_resolve.get("strategy"):
        case "fieldMap":
            field = graphql_type.interface_resolve.get("field")
            field_map = graphql_type.interface_resolve.get("fieldMap") or {}
            if (
                field
                and isinstance(data, dict)
                and (field_value := data.get(field))
                and (name := field_map.get(field_value))
            ):
                return bundle.graphql_lookup.get_by_type_name(name)
            return None
        case _:
            return None


def _resolve_schema(
    schema_path: str | None,
    schema: Any,
    bundle: Bundle,
    data: Any,
    graphql_type: GraphqlTypeV2 | None,
) -> tuple[str | None, Any]:
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
        "oneOf" in schema
        and graphql_type
        and graphql_type.interface_resolve
        and (field := graphql_type.interface_resolve.get("field"))
        and (field_value := data.get(field))
    ):
        new_schema = next(
            (
                one
                for one in schema["oneOf"] or []
                if isinstance(one, dict)
                and field_value
                in one.get("properties", {}).get(field, {}).get("enum", [])
            ),
            None,
        )
        return schema_path, new_schema
    return schema_path, schema


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
        schema = bundle.schemas.get(datafile_schema, {}) if datafile_schema else None
        graphql_type_name = (
            resolved_graphql_type.name
            if (
                datafile_schema
                and (
                    graphql_type := bundle.graphql_lookup.get_by_schema(datafile_schema)
                )
                and (
                    resolved_graphql_type := _resolve_graphql_type(
                        graphql_type, bundle, datafile
                    )
                )
            )
            else None
        )
        node = Node(
            bundle=bundle,
            data=datafile,
            graphql_field_name=None,
            graphql_type_name=graphql_type_name,
            jsonpaths=[],
            path=datafile_path,
            schema=schema,
            schema_path=datafile_schema,
        )
        yield from _traverse_node(node)
