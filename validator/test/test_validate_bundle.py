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
    return f"{result['kind']}:{result['filename']}"


def test_validate_bundle_schema(
    bundle_and_expected_results_factory: Callable[
        [str], tuple[Bundle, list[ValidationResult]]
    ],
) -> None:
    bundle, expected_results = bundle_and_expected_results_factory("schema_ok.yml")
    results = validate_bundle(bundle)
    assert sorted(results, key=validation_result_key) == sorted(
        expected_results, key=validation_result_key
    )
