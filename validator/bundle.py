import json
from collections.abc import Mapping
from dataclasses import (
    dataclass,
    field,
)
from functools import cached_property
from typing import (
    IO,
    Any,
    NotRequired,
    Optional,
    TypedDict,
)

RESOURCE_REF = "/common-1.json#/definitions/resourceref"


class InvalidBundleError(Exception):
    pass


@dataclass
class GraphqlType:
    type: str
    spec: dict[str, Any]
    bundle: "Bundle"

    def __post_init__(self):  # noqa: D105
        self.fields_by_name = {f.get("name"): f for f in self.spec.get("fields")}

    def get_referenced_field_type(self, name: str) -> Optional["GraphqlType"]:
        field = self.fields_by_name.get(name)
        if field:
            return self.bundle.get_graphql_type_by_name(field.get("type"))
        return None

    def get_interface_resolver_field(self) -> str | None:
        return self.spec.get("interfaceResolve", {}).get("field")

    def get_sub_type(self, discriminator: str) -> Optional["GraphqlType"]:
        sub_type_name = (
            self.spec.get("interfaceResolve", {}).get("fieldMap", {}).get(discriminator)
        )
        if sub_type_name:
            return self.bundle.get_graphql_type_by_name(sub_type_name)
        return None


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
class GraphqlTypeV2:
    name: str
    fields: dict[str, GraphqlField]
    datafile: str | None
    is_interface: bool
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

    def resolve_interface_field_value(self, data: Any) -> Any:
        if (field_name := self.interface_resolve_field_name()) and isinstance(
            data, dict
        ):
            return data.get(field_name)
        return None

    def resolve_interface_type_name(self, data: Any) -> str | None:
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
    def __init__(self, confs: list[dict[str, Any]]):
        self.graphql_types = {
            name: self._build_graphql_type(conf)
            for conf in confs
            if (name := conf.get("name"))
        }
        self.type_name_by_schema = self._build_type_name_by_schema(
            graphql_types=self.graphql_types,
        )

    @staticmethod
    def _build_graphql_type(conf: Mapping[str, Any]) -> GraphqlTypeV2:
        fields = {
            field_name: field
            for field in conf.get("fields") or []
            if (field_name := field.get("name"))
        }
        return GraphqlTypeV2(
            name=conf["name"],
            fields=fields,
            datafile=conf.get("datafile"),
            is_interface=conf.get("isInterface", False),
            interface_resolve=conf.get("interfaceResolve"),
        )

    @staticmethod
    def _build_type_name_by_schema(
        graphql_types: dict[str, GraphqlTypeV2],
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

    def get_by_type_name(self, name: str) -> GraphqlTypeV2 | None:
        return self.graphql_types.get(name)

    def get_by_schema(self, schema: str) -> GraphqlTypeV2 | None:
        if name := self.type_name_by_schema.get(schema):
            return self.get_by_type_name(name)
        return None


@dataclass
class Bundle:
    graphql: list[dict[str, Any]] | dict[str, Any]
    data: dict[str, dict[str, Any]]
    schemas: dict[str, dict[str, Any]]
    resources: dict[str, dict[str, Any]]
    git_commit: str
    git_commit_timestamp: str

    _schema_to_graphql_type: dict[str, GraphqlType] = field(init=False)
    _top_level_schemas: set[str] = field(init=False)
    _graphql_type_by_name: dict[str, GraphqlType] = field(init=False)

    @cached_property
    def graphql_lookup(self) -> GraphqlLookup:
        if isinstance(self.graphql, dict):
            confs = self.graphql.get("confs", [])
            return GraphqlLookup(confs)
        return GraphqlLookup(self.graphql)

    def __post_init__(self):  # noqa: D105
        if isinstance(self.graphql, dict) and (self.graphql["confs"]):
            self._graphql_type_by_name = {
                t["name"]: GraphqlType(t["name"], t, self)
                for t in self.graphql["confs"]
            }
        elif isinstance(self.graphql, list):
            self._graphql_type_by_name = {
                t["name"]: GraphqlType(t["name"], t, self) for t in self.graphql
            }
        else:
            msg = (
                "graphql field within bundle must be either "
                "`list` or `dict` with keys `$schema` and `confs`"
            )
            raise InvalidBundleError(msg)
        # use the datafile field on the graphql type to map to the schema
        self._schema_to_graphql_type = {
            f.get("datafile"): self._graphql_type_by_name[f["name"]]
            for f in self.graphql.get("confs", [])
            if f.get("datafile")
        }
        # also use the datafileSchema field within the Query section
        self._schema_to_graphql_type.update({
            f.get("datafileSchema"): self._graphql_type_by_name[f["type"]]
            for f in self._graphql_type_by_name["Query"].spec["fields"]
            if f.get("datafileSchema")
        })
        self._top_level_schemas = {
            f.get("datafileSchema")
            for f in self._graphql_type_by_name["Query"].spec["fields"]
            if f.get("datafileSchema")
        }

    def to_dict(self):
        return {
            "git_commit": self.git_commit,
            "git_commit_timestamp": self.git_commit_timestamp,
            "schemas": self.schemas,
            "graphql": self.graphql,
            "data": self.data,
            "resources": self.resources,
        }

    def get_graphql_type_for_schema(self, schema: str) -> GraphqlType | None:
        return self._schema_to_graphql_type.get(schema)

    def list_graphql_types(self) -> list[GraphqlType]:
        return list(self._graphql_type_by_name.values())

    def get_graphql_type_by_name(self, prop_type: str) -> GraphqlType | None:
        return self._graphql_type_by_name.get(prop_type)

    def is_top_level_schema(self, datafile_schema: str) -> bool:
        return datafile_schema in self._top_level_schemas


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
