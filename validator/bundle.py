import json
from collections.abc import Iterable, Mapping
from dataclasses import (
    dataclass,
)
from functools import cached_property
from typing import (
    IO,
    Any,
    NotRequired,
    TypedDict,
)

RESOURCE_REF = "/common-1.json#/definitions/resourceref"


class InterfaceResolve(TypedDict):
    strategy: str
    fieldMap: NotRequired[dict[str, str]]
    field: NotRequired[str]


class GraphqlField(TypedDict):
    name: str
    type: str
    isUnique: NotRequired[bool]
    isContextUnique: NotRequired[bool]
    datafileSchema: NotRequired[str]


@dataclass(frozen=True)
class GraphqlType:
    name: str
    fields: dict[str, GraphqlField]
    datafile: str | None
    is_interface: bool
    interface: str | None
    interface_resolve: InterfaceResolve | None

    def get_field(self, field_name: str) -> GraphqlField | None:
        return self.fields.get(field_name)

    def is_interface_field_map(self) -> bool:
        return (
            self.is_interface
            and self.interface_resolve is not None
            and self.interface_resolve.get("strategy") == "fieldMap"
        )

    def interface_resolve_field_name(self) -> str | None:
        if self.is_interface_field_map() and self.interface_resolve:
            return self.interface_resolve.get("field")
        return None

    def resolve_interface_field_value(self, data: Any) -> Any:  # noqa: ANN401
        if (field_name := self.interface_resolve_field_name()) and isinstance(
            data, dict
        ):
            return data.get(field_name)
        return None

    def resolve_interface_type_name(self, data: Any) -> str | None:  # noqa: ANN401
        if (
            self.interface_resolve
            and (field_map := self.interface_resolve.get("fieldMap"))
            and (field_value := self.resolve_interface_field_value(data))
        ):
            return field_map.get(field_value)
        return None

    @staticmethod
    def is_context_unique_field(graphql_field: GraphqlField) -> bool:
        """
        A field is context unique if isContextUnique is true, or if isUnique is true.

        As global uniqueness implies context uniqueness.

        Args:
            graphql_field (GraphqlField): The GraphQL field to check.
        Returns:
            bool: True if the field is context unique, False otherwise.
        """
        return graphql_field.get(
            "isContextUnique",
            False,
        ) or graphql_field.get(
            "isUnique",
            False,
        )

    def context_unique_field_names(self) -> set[str]:
        return {
            field_name
            for field_name, field in self.fields.items()
            if self.is_context_unique_field(field)
        }


class GraphqlLookup:
    def __init__(self, confs: list[dict[str, Any]]) -> None:
        self.graphql_types = {
            name: self._build_graphql_type(conf)
            for conf in confs
            if (name := conf.get("name"))
        }
        self.type_name_by_schema = self._build_type_name_by_schema(
            graphql_types=self.graphql_types,
        )
        self.top_level_graphql_type_names = self._build_top_level_graphql_type_names(
            graphql_types=self.graphql_types.values(),
            graphql_type_names_with_schema=self.type_name_by_schema.values(),
        )

    @staticmethod
    def _build_graphql_type(conf: Mapping[str, Any]) -> GraphqlType:
        fields = {
            field_name: field
            for field in conf.get("fields") or []
            if (field_name := field.get("name"))
        }
        return GraphqlType(
            name=conf["name"],
            fields=fields,
            datafile=conf.get("datafile"),
            is_interface=conf.get("isInterface", False),
            interface=conf.get("interface"),
            interface_resolve=conf.get("interfaceResolve"),
        )

    @staticmethod
    def _build_top_level_graphql_type_names(
        graphql_types: Iterable[GraphqlType],
        graphql_type_names_with_schema: Iterable[str],
    ) -> set[str]:
        graphql_type_names = set(graphql_type_names_with_schema)
        for graphql_type in graphql_types:
            if graphql_type.interface and (
                graphql_type.interface in graphql_type_names
            ):
                graphql_type_names.add(graphql_type.name)
        return graphql_type_names

    @staticmethod
    def _build_type_name_by_schema(
        graphql_types: dict[str, GraphqlType],
    ) -> dict[str, str]:
        type_name_by_type_datafile = {
            datafile: type_name
            for type_name, graphql_type in graphql_types.items()
            if (datafile := graphql_type.datafile)
        }
        if query := graphql_types.get("Query"):
            type_name_by_query_datafile_schema = {
                datafile_schema: field["type"]
                for field in query.fields.values()
                if (datafile_schema := field.get("datafileSchema"))
            }
            return type_name_by_type_datafile | type_name_by_query_datafile_schema
        return type_name_by_type_datafile

    def get_by_type_name(self, name: str) -> GraphqlType | None:
        return self.graphql_types.get(name)

    def get_by_schema(self, schema: str) -> GraphqlType | None:
        if name := self.type_name_by_schema.get(schema):
            return self.get_by_type_name(name)
        return None


class Backref(TypedDict):
    path: str
    datafileSchema: str
    jsonpath: str


Resource = TypedDict(
    "Resource",
    {
        "path": str,
        "content": str,
        "$schema": str | None,
        "sha256sum": str,
        "backrefs": list[Backref],
    },
)


@dataclass(frozen=True)
class Bundle:
    graphql: list[dict[str, Any]] | dict[str, Any]
    data: dict[str, dict[str, Any]]
    schemas: dict[str, dict[str, Any]]
    resources: dict[str, Resource]
    git_commit: str
    git_commit_timestamp: str

    @cached_property
    def graphql_lookup(self) -> GraphqlLookup:
        if isinstance(self.graphql, dict):
            confs = self.graphql.get("confs", [])
            return GraphqlLookup(confs)
        return GraphqlLookup(self.graphql)


def load_bundle(bundle_source: IO) -> Bundle:
    bundle_data = json.load(bundle_source)
    return Bundle(
        data=bundle_data["data"],
        graphql=bundle_data["graphql"],
        schemas=bundle_data["schemas"],
        resources=bundle_data["resources"],
        git_commit=bundle_data["git_commit"],
        git_commit_timestamp=bundle_data["git_commit_timestamp"],
    )
