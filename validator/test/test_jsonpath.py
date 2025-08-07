from validator.jsonpath import (
    JSONPathField,
    JSONPathIndex,
    build_jsonpath,
    read_jsonpath,
)


def test_build_jsonpath() -> None:
    jsonpaths = [
        JSONPathField(field="name"),
        JSONPathIndex(index=0),
        JSONPathField(field="details"),
    ]

    jsonpath = build_jsonpath(jsonpaths)

    assert jsonpath == "name.[0].details"


def test_read_jsonpath() -> None:
    data = {
        "name": "example",
        "items": [
            {"details": "item1"},
        ],
    }
    jsonpaths = [
        JSONPathField(field="items"),
        JSONPathIndex(index=0),
        JSONPathField(field="details"),
    ]

    result = read_jsonpath(data, jsonpaths)

    assert result == "item1"
