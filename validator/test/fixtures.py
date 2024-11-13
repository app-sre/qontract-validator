from pathlib import Path

from validator.utils import parse_anymarkup_file


class Fixtures:
    def __init__(self, base_path):
        self.base_path = base_path

    def path(self, fixture):
        return Path(__file__).parent / "fixtures" / self.base_path / fixture

    def get(self, fixture):
        with Path.open(self.path(fixture), encoding="utf-8") as f:
            return f.read().strip()

    def get_anymarkup(self, fixture):
        data, _ = parse_anymarkup_file(self.path(fixture))
        return data
