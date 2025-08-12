from pathlib import Path

from validator.utils import parse_anymarkup_file


class Fixtures:
    def __init__(self, base_path: str):
        self.base_path = base_path

    def path(self, fixture: str) -> Path:
        return Path(__file__).parent / "fixtures" / self.base_path / fixture

    def get_anymarkup(self, fixture: str) -> dict:
        data, _ = parse_anymarkup_file(self.path(fixture))
        return data
