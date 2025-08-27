from collections.abc import Callable

import pytest

from validator.bundle import Bundle
from validator.postprocess_v2 import postprocess_bundle


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        (
            "unique_ok.yml",
            "unique_ok.expected.yml",
        ),
        (
            "context_unique_ok.yml",
            "context_unique_ok.expected.yml",
        ),
        (
            "context_unique_ref_array_duplicate.yml",
            "context_unique_ref_array_duplicate.expected.yml",
        ),
        (
            "unique_ref_array_duplicate.yml",
            "unique_ref_array_duplicate.expected.yml",
        ),
        (
            "context_unique_crossref_array_duplicate.yml",
            "context_unique_crossref_array_duplicate.expected.yml",
        ),
        (
            "context_unique_crossref_field.yml",
            "context_unique_crossref_field.expected.yml",
        ),
        (
            "unique_crossref_array_duplicate.yml",
            "unique_crossref_array_duplicate.expected.yml",
        ),
        (
            "unique_not_in_array.yml",
            "unique_not_in_array.yml",
        ),
        (
            "unique_ref_duplicate.yml",
            "unique_ref_duplicate.yml",
        ),
        (
            "unique_ref_array_duplicate_multiple_files.yml",
            "unique_ref_array_duplicate_multiple_files.expected.yml",
        ),
        (
            "unique_crossref_not_in_array.yml",
            "unique_crossref_not_in_array.yml",
        ),
        (
            "unique_crossref_array_duplicate_multiple_files.yml",
            "unique_crossref_array_duplicate_multiple_files.expected.yml",
        ),
    ],
)
def test_unique(
    bundle_fixture_factory: Callable[[str, str], Bundle],
    fixture: str,
    expected: str,
) -> None:
    bundle = bundle_fixture_factory("unique", fixture)
    expected_bundle = bundle_fixture_factory("unique", expected)

    postprocess_bundle(bundle)

    assert bundle.to_dict() == expected_bundle.to_dict()
