import os

from validator.utils import parse_anymarkup_file


class Fixtures(object):
    def __init__(self, base_path):
        self.base_path = base_path

    def path(self, fixture):
        return os.path.join(
            os.path.dirname(__file__),
            'fixtures',
            self.base_path,
            fixture
        )

    def get(self, fixture):
        with open(self.path(fixture), 'r') as f:
            return f.read().strip()

    def get_anymarkup(self, fixture):
        data, _ = parse_anymarkup_file(self.path(fixture))
        return data
