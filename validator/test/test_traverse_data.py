from operator import attrgetter

from validator.jsonpath import JSONPathField, JSONPathIndex, build_jsonpath
from validator.test.fixtures import get_bundle_fixture
from validator.traverse import Node, traverse_data


def test_traverse_data_simple_field() -> None:
    bundle = get_bundle_fixture("traverse_data", "simple_field.yml")

    nodes = list(traverse_data(bundle))

    assert nodes == [
        Node(
            bundle=bundle,
            data="bla",
            graphql_field_name="simple_field",
            graphql_type_name="Schema_v1",
            jsonpaths=[
                JSONPathField("simple_field"),
            ],
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
            graphql_type_name="Schema_v1",
            jsonpaths=[
                JSONPathField("array_field"),
                JSONPathIndex(0),
            ],
            path="file-1-schema-1.yml",
            schema={"type": "string"},
            schema_path="schema-1.yml",
        )
    ]


def test_traverse_data_simple_object_field() -> None:
    bundle = get_bundle_fixture("traverse_data", "simple_object_field.yml")

    nodes = list(traverse_data(bundle))

    assert nodes == [
        Node(
            bundle=bundle,
            data="bla",
            graphql_field_name="simple_nested_field",
            graphql_type_name="SimpleObject_v1",
            jsonpaths=[
                JSONPathField("simple_object"),
                JSONPathField("simple_nested_field"),
            ],
            path="file-1-schema-1.yml",
            schema={"type": "string"},
            schema_path="schema-1.yml",
        )
    ]


def test_traverse_data_simple_ref_field() -> None:
    bundle = get_bundle_fixture("traverse_data", "simple_ref_field.yml")

    nodes = list(traverse_data(bundle))

    assert nodes == [
        Node(
            bundle=bundle,
            data="/resource-1.yml",
            graphql_field_name="simple_ref",
            graphql_type_name="Schema_v1",
            jsonpaths=[
                JSONPathField("simple_ref"),
            ],
            path="file-1-schema-1.yml",
            schema={"$ref": "/common-1.json#/definitions/resourceref"},
            schema_path="schema-1.yml",
        )
    ]


def test_traverse_data_embedded_schema_ref_field() -> None:
    bundle = get_bundle_fixture("traverse_data", "embedded_schema_ref_field.yml")

    nodes = list(traverse_data(bundle))

    assert nodes == [
        Node(
            bundle=bundle,
            data="bla",
            graphql_field_name="simple_field",
            graphql_type_name="EmbeddedSchema_v1",
            jsonpaths=[
                JSONPathField("embedded_schema_ref_field"),
                JSONPathField("simple_field"),
            ],
            path="file-1-schema-1.yml",
            schema={"type": "string"},
            schema_path="embedded-schema-1.yml",
        )
    ]


def test_traverse_data_cross_ref_field() -> None:
    bundle = get_bundle_fixture("traverse_data", "cross_ref_field.yml")

    nodes = sorted(traverse_data(bundle), key=attrgetter("path"))

    assert nodes == [
        Node(
            bundle=bundle,
            data="file-2-another-schema-1.yml",
            graphql_field_name="crossref_field",
            graphql_type_name="Schema_v1",
            jsonpaths=[
                JSONPathField("crossref_field"),
                JSONPathField("$ref"),
            ],
            path="file-1-schema-1.yml",
            schema={
                "$ref": "/common-1.json#/definitions/crossref",
                "$schemaRef": "another-schema-1.yml",
            },
            schema_path="schema-1.yml",
        ),
        Node(
            bundle=bundle,
            data="bla",
            graphql_field_name="simple_field",
            graphql_type_name="AnotherSchema_v1",
            jsonpaths=[
                JSONPathField("simple_field"),
            ],
            path="file-2-another-schema-1.yml",
            schema={"type": "string"},
            schema_path="another-schema-1.yml",
        ),
    ]


def test_traverse_data_one_of_ref_array_field_map_field() -> None:
    bundle = get_bundle_fixture("traverse_data", "one_of_ref_array_field_map_field.yml")

    nodes = sorted(
        traverse_data(bundle), key=lambda n: f"{n.path}#{build_jsonpath(n.jsonpaths)}"
    )

    assert nodes == [
        Node(
            bundle=bundle,
            data="/resource-1.yml",
            graphql_field_name="a_field",
            graphql_type_name="SubType_v1",
            jsonpaths=[
                JSONPathField("one_of_ref_array"),
                JSONPathIndex(0),
                JSONPathField("a_field"),
            ],
            path="file-1-schema-1.yml",
            schema={"$ref": "/common-1.json#/definitions/resourceref"},
            schema_path="one-of-type-1.yml",
        ),
        Node(
            bundle=bundle,
            data="flavour-1",
            graphql_field_name="type_field",
            graphql_type_name="SubType_v1",
            jsonpaths=[
                JSONPathField("one_of_ref_array"),
                JSONPathIndex(0),
                JSONPathField("type_field"),
            ],
            path="file-1-schema-1.yml",
            schema={"type": "string", "enum": ["flavour-1"]},
            schema_path="one-of-type-1.yml",
        ),
        Node(
            bundle=bundle,
            data="bla",
            graphql_field_name="a_field",
            graphql_type_name="SubType_v2",
            jsonpaths=[
                JSONPathField("one_of_ref_array"),
                JSONPathIndex(1),
                JSONPathField("a_field"),
            ],
            path="file-1-schema-1.yml",
            schema={"type": "string"},
            schema_path="one-of-type-1.yml",
        ),
        Node(
            bundle=bundle,
            data="flavour-2",
            graphql_field_name="type_field",
            graphql_type_name="SubType_v2",
            jsonpaths=[
                JSONPathField("one_of_ref_array"),
                JSONPathIndex(1),
                JSONPathField("type_field"),
            ],
            path="file-1-schema-1.yml",
            schema={"type": "string", "enum": ["flavour-2"]},
            schema_path="one-of-type-1.yml",
        ),
    ]


def test_traverse_data_one_of_ref_field_map_field() -> None:
    bundle = get_bundle_fixture("traverse_data", "one_of_ref_field_map_field.yml")

    nodes = sorted(
        traverse_data(bundle), key=lambda n: f"{n.path}#{build_jsonpath(n.jsonpaths)}"
    )

    assert nodes == [
        Node(
            bundle=bundle,
            data="/resource-1.yml",
            graphql_field_name="a_field",
            graphql_type_name="SubType_v1",
            jsonpaths=[
                JSONPathField("one_of_ref"),
                JSONPathField("a_field"),
            ],
            path="file-1-schema-1.yml",
            schema={"$ref": "/common-1.json#/definitions/resourceref"},
            schema_path="one-of-type-1.yml",
        ),
        Node(
            bundle=bundle,
            data="flavour-1",
            graphql_field_name="type_field",
            graphql_type_name="SubType_v1",
            jsonpaths=[
                JSONPathField("one_of_ref"),
                JSONPathField("type_field"),
            ],
            path="file-1-schema-1.yml",
            schema={"type": "string", "enum": ["flavour-1"]},
            schema_path="one-of-type-1.yml",
        ),
        Node(
            bundle=bundle,
            data="bla",
            graphql_field_name="a_field",
            graphql_type_name="SubType_v2",
            jsonpaths=[
                JSONPathField("one_of_ref"),
                JSONPathField("a_field"),
            ],
            path="file-2-schema-1.yml",
            schema={"type": "string"},
            schema_path="one-of-type-1.yml",
        ),
        Node(
            bundle=bundle,
            data="flavour-2",
            graphql_field_name="type_field",
            graphql_type_name="SubType_v2",
            jsonpaths=[
                JSONPathField("one_of_ref"),
                JSONPathField("type_field"),
            ],
            path="file-2-schema-1.yml",
            schema={"type": "string", "enum": ["flavour-2"]},
            schema_path="one-of-type-1.yml",
        ),
    ]
