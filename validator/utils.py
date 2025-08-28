import hashlib
import json
from enum import StrEnum
from pathlib import Path, PurePath
from typing import IO, Any

import yaml

JSON_COMPACT_SEPARATORS = (",", ":")


class FileType(StrEnum):
    YAML = "yaml"
    JSON = "json"


SUPPORTED_EXTENSIONS = {
    ".yaml": FileType.YAML,
    ".yml": FileType.YAML,
    ".json": FileType.JSON,
}


def get_file_type(path: PurePath) -> FileType | None:
    return SUPPORTED_EXTENSIONS.get(path.suffix)


def get_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(data: str | bytes) -> dict:
    if hasattr(yaml, "CSafeLoader"):
        return yaml.load(data, Loader=yaml.CSafeLoader)
    return yaml.load(data, Loader=yaml.SafeLoader)


def json_dumps(
    data: Any,  # noqa: ANN401,
    *,
    compact: bool = False,
    indent: int | None = None,
    sort_keys: bool = False,
) -> str:
    separators = JSON_COMPACT_SEPARATORS if compact else None
    return json.dumps(
        data,
        indent=indent,
        separators=separators,
        sort_keys=sort_keys,
    )


def json_dump(
    data: Any,  # noqa: ANN401
    out: IO,
    *,
    compact: bool = False,
    indent: int | None = None,
    sort_keys: bool = False,
) -> None:
    separators = JSON_COMPACT_SEPARATORS if compact else None
    json.dump(
        data,
        out,
        indent=indent,
        separators=separators,
        sort_keys=sort_keys,
    )
    out.write("\n")


def parse_anymarkup_file(
    path: Path,
    checksum_field_name: str | None = None,
) -> tuple[dict, str | None]:
    match get_file_type(path):
        case FileType.YAML:
            content = path.read_bytes()
            res = load_yaml(content)
        case FileType.JSON:
            content = path.read_bytes()
            res = json.loads(content)
        case _:
            msg = f"markup parsing for extension {path.suffix} is not implemented"
            raise NotImplementedError(msg)
    checksum = get_checksum(content) if checksum_field_name else None
    return res, checksum
