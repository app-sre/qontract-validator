import validator.validator as validator
from validator.test.fixtures import Fixtures


class TestGetSchemaInfoFromPointer(object):
    fxt = Fixtures('get_schema_info_from_pointer')

    def do_fxt_test(self, fxt_path):
        fixture = self.fxt.get_anymarkup(self.fxt.path(fxt_path))

        obj = validator.get_schema_info_from_pointer(
            fixture['schema'], fixture['ptr'],
            fixture.get('schemas_bundle', {}))

        assert fixture['magic'] == obj

    def test_object(self):
        self.do_fxt_test('object.yml')

    def test_object_array(self):
        self.do_fxt_test('object_array.yml')

    def test_object_object(self):
        self.do_fxt_test('object_object.yml')

    def test_complex(self):
        self.do_fxt_test('complex.yml')

    def test_external_ref(self):
        self.do_fxt_test('external_ref.yml')
