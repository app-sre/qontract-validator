from collections.abc import Callable
from typing import Any

import pytest

from validator.bundle import Bundle
from validator.test.fixtures import Fixtures

TEST_GIT_COMMIT = "git-commit-sha"
TEST_GIT_COMMIT_TIMESTAMP = "git-commit-timestamp"


@pytest.fixture
def fixture_factory() -> Callable[[str, str], Any]:
    def _fixture_factory(base_path: str, fixture: str) -> Any:
        return Fixtures(base_path).get_anymarkup(fixture)

    return _fixture_factory


@pytest.fixture
def file_factory() -> Callable[[str, str], str]:
    def _file_factory(base_path: str, fixture: str) -> str:
        return Fixtures(base_path).get_file_content(fixture)

    return _file_factory


@pytest.fixture
def bundle_factory() -> Callable[[dict[str, Any]], Bundle]:
    def _bundle_factory(fxt: dict[str, Any]) -> Bundle:
        return Bundle(
            git_commit=TEST_GIT_COMMIT,
            git_commit_timestamp=TEST_GIT_COMMIT_TIMESTAMP,
            schemas=fxt["schemas"],
            graphql=fxt["graphql"],
            data=fxt["data"],
            resources=fxt["resources"],
        )

    return _bundle_factory


@pytest.fixture
def bundle_fixture_factory(
    fixture_factory: Callable[[str, str], Any],
    bundle_factory: Callable[[dict[str, Any]], Bundle],
) -> Callable[[str, str], Bundle]:
    def _bundle_fixture_factory(base_path: str, fixture: str) -> Bundle:
        fxt = fixture_factory(base_path, fixture)
        return bundle_factory(fxt)

    return _bundle_fixture_factory
