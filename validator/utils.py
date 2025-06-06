import hashlib
import json
from enum import StrEnum
from pathlib import Path

import yaml


class FileType(StrEnum):
    YAML = "yaml"
    JSON = "json"


SUPPORTED_EXTENSIONS = {
    ".yaml": FileType.YAML,
    ".yml": FileType.YAML,
    ".json": FileType.JSON,
}


def get_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(data: bytes) -> dict:
    if hasattr(yaml, "CSafeLoader"):
        return yaml.load(data, Loader=yaml.CSafeLoader)
    return yaml.load(data, Loader=yaml.SafeLoader)


def parse_anymarkup_file(
    path: Path,
    checksum_field_name: str | None = None,
) -> tuple[dict, str | None]:
    match SUPPORTED_EXTENSIONS.get(path.suffix):
        case FileType.YAML:
            content = path.read_bytes()
            res = load_yaml(content)
        case FileType.JSON:
            content = path.read_bytes()
            res = _load_json(content)
        case _:
            msg = f"markup parsing for extension {path.suffix} is not implemented"
            raise NotImplementedError(msg)
    checksum = get_checksum(content) if checksum_field_name else None
    return res, checksum


def _load_json(data: bytes) -> dict:
    return json.loads(data)
