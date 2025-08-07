from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


class JSONPath(ABC):
    @abstractmethod
    def to_expression(self) -> str:
        pass

    @abstractmethod
    def read(self, data: Any) -> Any:
        pass


@dataclass(frozen=True)
class JSONPathField(JSONPath):
    field: str

    def to_expression(self) -> str:
        return self.field

    def read(self, data: Any) -> Any:
        return data.get(self.field)


@dataclass(frozen=True)
class JSONPathIndex(JSONPath):
    index: int

    def to_expression(self) -> str:
        return f"[{self.index}]"

    def read(self, data: Any) -> Any:
        return data[self.index]


def build_jsonpath(jsonpaths: Iterable[JSONPath]) -> str:
    """
    Build a JSONPath expression from a list of JsonPath objects.

    Args:
        jsonpaths (Iterable[JSONPath]): An iterable of JsonPath objects.
    Returns:
        str: A string representing the JSONPath expression.
    """
    return ".".join(path.to_expression() for path in jsonpaths)


def read_jsonpath(data: Any, jsonpaths: Iterable[JSONPath]) -> Any:
    """
    Read data from a JSON object using a list of JsonPath objects.
    Args:
        data (Any): The JSON object to read from.
        jsonpaths (Iterable[JSONPath]): An iterable of JsonPath objects.
    Returns:
        Any: The value extracted from the JSON object using the provided JsonPath objects.
    """
    result = data
    for path in jsonpaths:
        result = path.read(result)
    return result
