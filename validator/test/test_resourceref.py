import pytest

from validator.bundle import Bundle
from validator.postprocess import postprocess_bundle
from validator.test.fixtures import get_bundle_fixture


@pytest.fixture
def bundle(request) -> Bundle:
    return get_bundle_fixture("backref", "bundle.yml")


def test_simple_refs(bundle: Bundle):
    postprocess_bundle(bundle)
    expected = [
        {
            "path": "file-1-schema-1.yml",
            "datafileSchema": "schema-1.yml",
            "type": "Schema_v1",
            "jsonpath": "simple_ref",
        },
        {
            "path": "file-1-schema-1.yml",
            "datafileSchema": "schema-1.yml",
            "type": "Schema_v1",
            "jsonpath": "simple_object.simple_nested_ref",
        },
    ]
    resource = bundle.resources.get("/resource-1.yml")
    assert resource is not None
    assert expected == resource.get("backrefs")


def test_array_field_to_nested_refs(bundle: Bundle):
    postprocess_bundle(bundle)
    expected = [
        {
            "path": "file-1-schema-1.yml",
            "datafileSchema": "schema-1.yml",
            "type": "Schema_v1",
            "jsonpath": "array_field_to_nested_refs.[0].simple_nested_ref",
        },
        {
            "path": "file-1-schema-1.yml",
            "datafileSchema": "schema-1.yml",
            "type": "Schema_v1",
            "jsonpath": "array_field_to_nested_refs.[1].simple_nested_ref",
        },
    ]
    resource = bundle.resources.get("/resource-3.yml")
    assert resource is not None
    assert expected == resource.get("backrefs")


def test_embedded_schemas(bundle):
    """shows that resourceref detection works for embedded types ($ref)"""
    postprocess_bundle(bundle)

    expected = [
        {
            "path": "file-1-schema-1.yml",
            "datafileSchema": "schema-1.yml",
            "type": "Schema_v1",
            "jsonpath": "schema_ref_field.simple_ref",
        },
        {
            "path": "file-1-schema-1.yml",
            "datafileSchema": "schema-1.yml",
            "type": "Schema_v1",
            "jsonpath": "schema_ref_field.simple_object.simple_nested_ref",
        },
    ]
    assert expected == bundle.resources.get("/resource-2.yml").get("backrefs")


def test_one_of_refs(bundle: Bundle):
    """this test shows that refs can be found in subtypes while the same field name can be a ref in one subtype but not in another"""
    postprocess_bundle(bundle)
    expected = [
        {
            "path": "file-1-schema-1.yml",
            "datafileSchema": "schema-1.yml",
            "type": "Schema_v1",
            "jsonpath": "one_of_ref_array.[0].a_field",
        },
        {
            "path": "file-1-schema-1.yml",
            "datafileSchema": "schema-1.yml",
            "type": "Schema_v1",
            "jsonpath": "one_of_ref_array.[2].a_field",
        },
    ]
    resource = bundle.resources.get("/resource-4.yml")
    assert resource is not None
    assert expected == resource.get("backrefs")


def test_circular_ref_top_level_type(bundle: Bundle):
    """shows that reference loops are dealth with an reference detection stops looking in other top level types"""
    postprocess_bundle(bundle)
    expected = [
        {
            "path": "file-2-another-schema-1.yml",
            "datafileSchema": "another-schema-1.yml",
            "type": "AnotherSchema_v1",
            "jsonpath": "simple_ref",
        },
        {
            "path": "file-2-another-schema-1.yml",
            "datafileSchema": "another-schema-1.yml",
            "type": "AnotherSchema_v1",
            "jsonpath": "simple_object.simple_nested_ref",
        },
    ]
    resource = bundle.resources.get("/resource-5.yml")
    assert resource is not None
    assert expected == resource.get("backrefs")
