from collections.abc import Callable
from typing import Any

import pytest

from validator.bundle import Bundle
from validator.test.fixtures import Fixtures


@pytest.fixture
def fixture_factory() -> Callable[[str, str], Any]:
    def _fixture_factory(base_path: str, fixture: str) -> Any:
        return Fixtures(base_path).get_anymarkup(fixture)

    return _fixture_factory


@pytest.fixture
def bundle_factory() -> Callable[[dict[str, Any]], Bundle]:
    def _bundle_factory(fxt: dict[str, Any]) -> Bundle:
        return Bundle(
            git_commit="c",
            git_commit_timestamp="t",
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
