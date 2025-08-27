from collections.abc import Callable
from typing import Any

import pytest

from validator.bundle import Bundle
from validator.validator import ValidationResult, validate_bundle


@pytest.fixture
def metaschema_schema(
    fixture_factory: Callable[[str, str], Any],
) -> dict[str, Any]:
    return fixture_factory("validator", "metaschema-1.json")


@pytest.fixture
def json_schema_spec_draft_06_schema(
    fixture_factory: Callable[[str, str], Any],
) -> dict[str, Any]:
    return fixture_factory("validator", "json-schema-spec-draft-06.json")


@pytest.fixture
def common_schema(
    fixture_factory: Callable[[str, str], Any],
) -> dict[str, Any]:
    return fixture_factory("validator", "common-1.json")


@pytest.fixture
def graphql_schema(
    fixture_factory: Callable[[str, str], Any],
) -> dict[str, Any]:
    return fixture_factory("validator", "graphql-schemas-1.yml")


@pytest.fixture
def bundle_and_expected_results_factory(
    fixture_factory: Callable[[str, str], Any],
    bundle_factory: Callable[[dict[str, Any]], Bundle],
    common_schema: dict[str, Any],
    metaschema_schema: dict[str, Any],
    json_schema_spec_draft_06_schema: dict[str, Any],
    graphql_schema: dict[str, Any],
) -> Callable[[str], tuple[Bundle, list[ValidationResult]]]:
    def _bundle_and_expected_results_factory(
        fixture: str,
    ) -> tuple[Bundle, list[ValidationResult]]:
        fxt = fixture_factory("validator", fixture)
        fxt["schemas"]["/common-1.json"] = common_schema
        fxt["schemas"]["/metaschema-1.json"] = metaschema_schema
        fxt["schemas"]["/json-schema-spec-draft-06.json"] = (
            json_schema_spec_draft_06_schema
        )
        fxt["schemas"]["/app-interface/graphql-schemas-1.yml"] = graphql_schema
        bundle = bundle_factory(fxt)
        expected_results = list(fxt.get("expected_results", []))
        return bundle, expected_results

    return _bundle_and_expected_results_factory


def validation_result_key(result: ValidationResult) -> str:
    return ":".join([
        result["filename"],
        result["kind"],
        result["result"]["status"],
    ])


@pytest.mark.parametrize(
    "fixture",
    [
        "valid.yml",
        "schema_missing_schema_url.yml",
        "schema_validation_error.yml",
        "schema_schema_error.yml",
        "file_missing_schema_url.yml",
        "file_missing_schema_url_graphql.yml",
        "file_schema_not_found.yml",
        "file_validation_error.yml",
        "file_validation_error_graphql.yml",
        "file_resource_file_not_found.yml",
        "duplicate_unique_fields.yml",
        "duplicate_unique_interface_fields.yml",
        "duplicate_context_unique_fields.yml",
        "duplicate_context_unique_crossref_fields.yml",
        "resource_invalid_yaml_skip.yml",
        "resource_schema_not_found.yml",
        "resource_validation_error.yml",
        "ref_file_not_found.yml",
        "ref_incorrect_schema.yml",
        "ref_schema_ref_validation_error.yml",
        "graphql_is_unique_on_non_top_level_type.yml",
        "graphql_is_unique_on_complex_field.yml",
    ],
)
def test_validate_bundle(
    bundle_and_expected_results_factory: Callable[
        [str], tuple[Bundle, list[ValidationResult]]
    ],
    fixture: str,
) -> None:
    bundle, expected_results = bundle_and_expected_results_factory(fixture)

    results = validate_bundle(bundle)

    assert len(results) == len(expected_results)
    for result, expected in zip(
        sorted(results, key=validation_result_key),
        sorted(expected_results, key=validation_result_key),
        strict=True,
    ):
        assert result["kind"] == expected["kind"]
        assert result["filename"] == expected["filename"]
        assert result["result"]["summary"] == expected["result"]["summary"]
        assert result["result"]["status"] == expected["result"]["status"]
        assert result["result"].get("schema_url") == expected["result"].get(
            "schema_url"
        )
        assert result["result"].get("reason") == expected["result"].get("reason")
        assert expected["result"].get("error", "") in result["result"].get("error", "")
