from collections.abc import Callable
from typing import Any

import pytest

from validator.bundle import Bundle
from validator.jsonpath import (
    build_jsonpath,
    parse_jsonpath,
)
from validator.traverse import Node, traverse_data


def parse_node(node: dict[str, Any], bundle: Bundle) -> Node:
    parent = parse_node(node.get("parent"), bundle) if node.get("parent") else None
    return Node(
        bundle=bundle,
        data=node.get("data"),
        file_schema_path=node.get("file_schema_path"),
        graphql_field_name=node.get("graphql_field_name"),
        graphql_type_name=node.get("graphql_type_name"),
        jsonpaths=parse_jsonpath(node.get("jsonpath", "")),
        path=node["path"],
        schema=node.get("schema"),
        schema_path=node.get("schema_path"),
        parent=parent,
    )


@pytest.fixture
def bundle_and_expected_nodes_factory(
    fixture_factory: Callable[[str, str], Any],
    bundle_factory: Callable[[dict[str, Any]], Bundle],
) -> Callable[[str, str], tuple[Bundle, list[Node]]]:
    def _bundle_and_expected_nodes_factory(
        base_path: str, fixture: str
    ) -> tuple[Bundle, list[Node]]:
        fxt = fixture_factory(base_path, fixture)
        bundle = bundle_factory(fxt)
        expected_nodes = [
            parse_node(node, bundle)
            for node in fxt.get("expected_nodes", [])
        ]
        return bundle, expected_nodes

    return _bundle_and_expected_nodes_factory


@pytest.mark.parametrize(
    "fixture",
    [
        "array_field.yml",
        "crossref_field.yml",
        "crossref_interface_schema_field.yml",
        "embedded_schema_ref_field.yml",
        "one_of_ref_array_field_map_field.yml",
        "one_of_ref_field_map_field.yml",
        "simple_field.yml",
        "simple_object_field.yml",
        "simple_ref_field.yml",
    ],
)
def test_traverse_data(
    bundle_and_expected_nodes_factory: Callable[[str, str], tuple[Bundle, list[Node]]],
    fixture: str,
) -> None:
    bundle, expected_nodes = bundle_and_expected_nodes_factory("traverse_data", fixture)

    nodes = sorted(
        traverse_data(bundle),
        key=lambda n: f"{n.path}#{build_jsonpath(n.jsonpaths)}",
    )

    assert nodes == expected_nodes
