from dataclasses import dataclass, field
import json
from typing import Any, Optional


@dataclass
class GraphqlType:

    type: str
    spec: dict[str, Any]
    bundle: "Bundle"

    def __post_init__(self):
        self.fields_by_name = {
            f.get("name"): f for f in self.spec.get("fields")
        }

    def get_referenced_field_type(self, name: str) -> Optional["GraphqlType"]:
        field = self.fields_by_name.get(name)
        if field:
            return self.bundle.get_graphql_type_by_name(field.get("type"))
        else:
            return None

    def get_interface_resolver_field(self) -> Optional[str]:
        return self.spec.get("interfaceResolve", {}).get("field")

    def get_sub_type(self, discriminator: str) -> Optional["GraphqlType"]:
        sub_type_name = self.spec.get("interfaceResolve", {}).get("fieldMap", {}).get(discriminator)
        if sub_type_name:
            return self.bundle.get_graphql_type_by_name(sub_type_name)
        else:
            return None


@dataclass
class Bundle:

    graphql: list[dict[str, Any]]
    data: dict[str, dict[str, Any]]
    schemas: dict[str, dict[str, Any]]
    resources: dict[str, dict[str, Any]]
    git_commit: str
    git_commit_timestamp: str

    _top_level_schemas: dict[str, GraphqlType] = field(init=False)
    _graphql_type_by_name: dict[str, GraphqlType] = field(init=False)

    def __post_init__(self):
        self._graphql_type_by_name = {t["name"]: GraphqlType(t["name"], t, self) for t in self.graphql}
        self._top_level_schemas = {
            f.get("datafileSchema"): self._graphql_type_by_name[f["type"]]
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
            "resources": self.resources
        }

    def get_graphql_type_for_schema(self, schema) -> Optional[GraphqlType]:
        return self._top_level_schemas.get(schema)

    def get_graphql_type_by_name(self, type: str) -> Optional[GraphqlType]:
        return self._graphql_type_by_name.get(type)

    def is_top_level_schema(self, datafile_schema) -> bool:
        return datafile_schema in self._top_level_schemas


def load_bundle(bundle_source) -> Bundle:
    bundle_data = json.load(bundle_source)
    return Bundle(
        data=bundle_data["data"],
        graphql=bundle_data["graphql"],
        schemas=bundle_data["schemas"],
        resources=bundle_data["resources"],
        git_commit=bundle_data["git_commit"],
        git_commit_timestamp=bundle_data["git_commit_timestamp"],
    )
