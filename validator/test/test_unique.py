from copy import deepcopy

import pytest

from validator.bundle import Bundle
from validator.postprocess import postprocess_bundle
from validator.test.fixtures import Fixtures


def get_bundle_fixture(name: str) -> Bundle:
    fxt = Fixtures("unique")
    fixture = fxt.get_anymarkup(fxt.path(name))
    return Bundle(
        git_commit="c",
        git_commit_timestamp="t",
        schemas=fixture["schemas"],
        graphql=fixture["graphql"],
        data=fixture["data"],
        resources=fixture["resources"],
    )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "context_unique_ok.yml",
        "unique_ok.yml",
    ],
)
def test_ok(fixture_name: str) -> None:
    bundle = get_bundle_fixture(fixture_name)
    expected_bundle_dict = deepcopy(bundle.to_dict())
    expected_bundle_dict["schemas"]["another-schema-1.yml"]["properties"][
        "__identifier"
    ] = {
        "type": "string",
    }
    expected_bundle_dict["data"]["file-1-schema-1.yml"]["ref_array"][0][
        "__identifier"
    ] = "128ecf542a35ac5270a87dc740918404"
    expected_bundle_dict["data"]["file-2-another-schema-1.yml"][
        "__identifier"
    ] = "128ecf542a35ac5270a87dc740918404"

    errors = postprocess_bundle(bundle)

    assert errors == []
    assert bundle.to_dict() == expected_bundle_dict


@pytest.mark.parametrize(
    "fixture_name",
    [
        "context_unique_ref_array_duplicate.yml",
        "unique_ref_array_duplicate.yml",
        "context_unique_crossref_array_duplicate.yml",
        "unique_crossref_array_duplicate.yml",
    ],
)
def test_duplicate(fixture_name: str) -> None:
    bundle = get_bundle_fixture(fixture_name)

    errors = postprocess_bundle(bundle)

    assert len(errors) == 1


def test_unique_duplicate() -> None:
    bundle = get_bundle_fixture("unique_duplicate.yml")
    expected_bundle_dict = deepcopy(bundle.to_dict())
    expected_bundle_dict["schemas"]["schema-1.yml"]["properties"][
        "__identifier"
    ] = {
        "type": "string",
    }

    errors = postprocess_bundle(bundle)

    assert errors == []
    assert bundle.to_dict() == expected_bundle_dict


def test_unique_ref_duplicate() -> None:
    bundle = get_bundle_fixture("unique_ref_duplicate.yml")
    expected_bundle_dict = deepcopy(bundle.to_dict())
    expected_bundle_dict["schemas"]["another-schema-1.yml"]["properties"][
        "__identifier"
    ] = {
        "type": "string",
    }

    errors = postprocess_bundle(bundle)

    assert errors == []
    assert bundle.to_dict() == expected_bundle_dict


def test_unique_ref_array_duplicate_multiple_files() -> None:
    bundle = get_bundle_fixture("unique_ref_array_duplicate_multiple_files.yml")
    expected_bundle_dict = deepcopy(bundle.to_dict())
    expected_bundle_dict["schemas"]["another-schema-1.yml"]["properties"][
        "__identifier"
    ] = {
        "type": "string",
    }
    expected_bundle_dict["data"]["file-1-schema-1.yml"]["ref_array"][0][
        "__identifier"
    ] = "128ecf542a35ac5270a87dc740918404"
    expected_bundle_dict["data"]["file-2-schema-1.yml"]["ref_array"][0][
        "__identifier"
    ] = "128ecf542a35ac5270a87dc740918404"

    errors = postprocess_bundle(bundle)

    assert errors == []
    assert bundle.to_dict() == expected_bundle_dict


def test_unique_crossref_duplicate() -> None:
    bundle = get_bundle_fixture("unique_crossref_duplicate.yml")
    expected_bundle_dict = deepcopy(bundle.to_dict())
    expected_bundle_dict["schemas"]["another-schema-1.yml"]["properties"][
        "__identifier"
    ] = {
        "type": "string",
    }

    errors = postprocess_bundle(bundle)

    assert errors == []
    assert bundle.to_dict() == expected_bundle_dict


def test_unique_crossref_array_duplicate_multiple_files() -> None:
    bundle = get_bundle_fixture("unique_crossref_array_duplicate_multiple_files.yml")
    expected_bundle_dict = deepcopy(bundle.to_dict())
    expected_bundle_dict["schemas"]["another-schema-1.yml"]["properties"][
        "__identifier"
    ] = {
        "type": "string",
    }
    expected_bundle_dict["data"]["file-2-another-schema-1.yml"][
        "__identifier"
    ] = "128ecf542a35ac5270a87dc740918404"

    errors = postprocess_bundle(bundle)

    assert errors == []
    assert bundle.to_dict() == expected_bundle_dict
