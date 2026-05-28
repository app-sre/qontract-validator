import json
from dataclasses import asdict
from io import StringIO
from typing import TYPE_CHECKING
from unittest.mock import patch

from validator.bundler import main
from validator.test.conftest import TEST_GIT_COMMIT, TEST_GIT_COMMIT_TIMESTAMP

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from validator.bundle import Bundle


def test_bundler_main(
    tmp_path: Path,
    file_factory: Callable[[str, str], str],
    bundle_fixture_factory: Callable[[str, str], Bundle],
) -> None:
    expected_bundle = bundle_fixture_factory("bundler", "bundle.expected.yml")

    schema_1 = file_factory("bundler", "schema-1.yml")
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "schema-1.yml").write_text(schema_1)

    file_1_schema_1 = file_factory("bundler", "file-1-schema-1.yml")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file-1-schema-1.yml").write_text(file_1_schema_1)

    resource_1 = file_factory("bundler", "resource-1.yml")
    resource_dir = tmp_path / "resources"
    resource_dir.mkdir()
    (resource_dir / "resource-1.yml").write_text(resource_1)

    graphql_schema = file_factory("bundler", "graphql-schema.yml")
    graphql_file = tmp_path / "graphql-schemas" / "schema.yml"
    graphql_file.parent.mkdir()
    graphql_file.write_text(graphql_schema)

    mock_args = [
        "qontract-bundler",
        "--thread-pool-size",
        "5",
        str(schema_dir),
        str(graphql_file),
        str(data_dir),
        str(resource_dir),
        TEST_GIT_COMMIT,
        TEST_GIT_COMMIT_TIMESTAMP,
    ]

    captured_output = StringIO()
    with (
        patch("sys.argv", mock_args),
        patch("sys.stdout", captured_output),
    ):
        main()

    output = captured_output.getvalue()
    assert json.loads(output) == asdict(expected_bundle)
