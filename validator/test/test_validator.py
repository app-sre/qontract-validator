from validator import validator
from validator.test.fixtures import Fixtures


class TestGetSchemaInfoFromPointer:
    fxt = Fixtures("get_schema_info_from_pointer")

    def do_fxt_test(self, fxt_path):
        fixture = self.fxt.get_anymarkup(self.fxt.path(fxt_path))

        obj = validator.get_schema_info_from_pointer(
            fixture["schema"], fixture["ptr"], fixture.get("schemas_bundle", {})
        )

        assert fixture["result"] == obj

    def test_object(self):
        self.do_fxt_test("object.yml")

    def test_object_array(self):
        self.do_fxt_test("object_array.yml")

    def test_object_object(self):
        self.do_fxt_test("object_object.yml")

    def test_complex(self):
        self.do_fxt_test("complex.yml")

    def test_external_ref(self):
        self.do_fxt_test("external_ref.yml")

    def test_one_of(self):
        self.do_fxt_test("one_of.yml")

    def test_one_of_multiple(self):
        self.do_fxt_test("one_of_multiple.yml")

    def test_external_ref_obj(self):
        self.do_fxt_test("external_ref_obj.yml")

    def test_external_ref_obj_oneof(self):
        self.do_fxt_test("external_ref_obj_oneof.yml")
