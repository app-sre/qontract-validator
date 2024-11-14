import hashlib
import json
from pathlib import Path

import yaml


def parse_anymarkup_file(filename, calc_checksum=None):
    if calc_checksum is None:
        calc_checksum = False
    if not Path(filename).is_file():
        msg = f"could not find file {filename}"
        raise FileNotFoundError(msg)

    file_ext = Path(filename).suffix[1:]

    res = {}
    if file_ext in {"yaml", "yml"}:
        with Path.open(filename, encoding="utf-8") as fh:
            content = fh.read()
            res = _load_yaml(content)
    elif file_ext == "json":
        with Path.open(filename, encoding="utf-8") as fh:
            content = fh.read()
            res = _load_json(content)
    else:
        msg = f"markup parsing for extension {file_ext} is not implemented"
        raise NotImplementedError(msg)

    checksum = _checksum(content.encode()) if calc_checksum else None
    return res, checksum


def _load_json(data):
    return json.loads(data)


def _load_yaml(data):
    return yaml.safe_load(data)


def _checksum(data):
    m = hashlib.sha256()
    m.update(data)
    return m.hexdigest()
