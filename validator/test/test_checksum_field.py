from typing import TYPE_CHECKING

import pytest

from validator.postprocess import postprocess_bundle

if TYPE_CHECKING:
    from collections.abc import Callable

    from validator.bundle import Bundle


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("checksum_field.yml", "checksum_field.expected.yml"),
        ("no_checksum_field.yml", "no_checksum_field.yml"),
    ],
)
def test_checksum_field(
    bundle_fixture_factory: Callable[[str, str], Bundle],
    fixture: str,
    expected: str,
) -> None:
    bundle = bundle_fixture_factory("checksum", fixture)
    expected_bundle = bundle_fixture_factory("checksum", expected)

    postprocess_bundle(bundle, "$file_sha256sum")

    assert bundle == expected_bundle
