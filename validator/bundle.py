import json
from collections.abc import Iterable, Mapping
from dataclasses import (
    dataclass,
    field,
)
from functools import cached_property
from typing import (
    IO,
    Any,
    Optional,
    TypedDict,
    NotRequired,
)


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
    interfaceResolve: NotRequired[InterfaceResolve]
    datafileSchema: NotRequired[str]


class GraphqlLookup:
    def __init__(self, confs: list[Mapping[str, Any]]):
        self.confs = {
            name: self._build_conf(conf.get("fields") or [])
            for conf in confs
            if (name := conf.get("name"))
        }
        # datafile field in conf or datafileSchema field in Query.fields
        self.name_by_schema = {
            datafile: name
            for conf in confs
            if (name := conf.get("name")) and (datafile := conf.get("datafile"))
        } | {
            datafileSchema: field["type"]
            for field in self.confs.get("Query", {}).values()
            if (datafileSchema := field.get("datafileSchema"))
        }

    @staticmethod
    def _build_conf(fields: Iterable[GraphqlField]) -> dict[str, GraphqlField]:
        return {name: f for f in fields if (name := f.get("name"))}

    def get_field(self, name: str, field_name: str) -> GraphqlField | None:
        return self.confs.get(name, {}).get(field_name)

    def get_name(self, schema: str) -> str | None:
        return self.name_by_schema.get(schema)


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
        confs = (
            self.graphql["confs"] if isinstance(self.graphql, dict) else self.graphql
        )
        return GraphqlLookup(confs)

    def __post_init__(self):  # noqa: D105
        if isinstance(self.graphql, dict) and (
            self.graphql["confs"] and self.graphql["$schema"]
        ):
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
