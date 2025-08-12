from collections.abc import Callable
from copy import deepcopy

from validator.bundle import Bundle
from validator.postprocess import postprocess_bundle


def test_checksum_field(
    bundle_fixture_factory: Callable[[str, str], Bundle],
) -> None:
    bundle = bundle_fixture_factory("checksum", "checksum_field.yml")
    expected_bundle_dict = deepcopy(bundle.to_dict())
    expected_bundle_dict["schemas"]["schema-1.yml"]["properties"]["$file_sha256sum"] = {
        "type": "string",
        "description": "sha256sum of the datafile",
    }

    postprocess_bundle(bundle, "$file_sha256sum")

    assert bundle.to_dict() == expected_bundle_dict


def test_no_checksum_field(
    bundle_fixture_factory: Callable[[str, str], Bundle],
) -> None:
    bundle = bundle_fixture_factory("checksum", "no_checksum_field.yml")
    expected_bundle_dict = deepcopy(bundle.to_dict())

    postprocess_bundle(bundle, "$file_sha256sum")

    assert bundle.to_dict() == expected_bundle_dict
