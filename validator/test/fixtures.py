from pathlib import Path

from validator.bundle import Bundle
from validator.utils import parse_anymarkup_file


class Fixtures:
    def __init__(self, base_path: str):
        self.base_path = base_path

    def path(self, fixture: str) -> Path:
        return Path(__file__).parent / "fixtures" / self.base_path / fixture

    def get_anymarkup(self, fixture: str) -> dict:
        data, _ = parse_anymarkup_file(self.path(fixture))
        return data


def get_bundle_fixture(base_path: str, fixture: str) -> Bundle:
    fixture = Fixtures(base_path).get_anymarkup(fixture)
    return Bundle(
        git_commit="c",
        git_commit_timestamp="t",
        schemas=fixture["schemas"],
        graphql=fixture["graphql"],
        data=fixture["data"],
        resources=fixture["resources"],
    )
