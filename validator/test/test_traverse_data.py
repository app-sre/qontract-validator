from validator.jsonpath import JSONPathField, JSONPathIndex
from validator.test.fixtures import get_bundle_fixture
from validator.traverse import traverse_data, Node


def test_traverse_data_simple_field() -> None:
    bundle = get_bundle_fixture("traverse_data", "simple_field.yml")

    nodes = list(traverse_data(bundle))

    assert nodes == [
        Node(
            bundle=bundle,
            data="bla",
            graphql_field_name="simple_field",
            graphql_name="Schema_v1",
            jsonpaths=[JSONPathField("simple_field")],
            path="file-1-schema-1.yml",
            schema={"type": "string"},
            schema_path="schema-1.yml",
        )
    ]


def test_traverse_data_array_field() -> None:
    bundle = get_bundle_fixture("traverse_data", "array_field.yml")

    nodes = list(traverse_data(bundle))

    assert nodes == [
        Node(
            bundle=bundle,
            data="bla",
            graphql_field_name="array_field",
            graphql_name="Schema_v1",
            jsonpaths=[JSONPathField("array_field"), JSONPathIndex(0)],
            path="file-1-schema-1.yml",
            schema={"type": "string"},
            schema_path="schema-1.yml",
        )
    ]
