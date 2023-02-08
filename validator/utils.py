import hashlib
import json
import os

import yaml

try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader


def parse_anymarkup_file(filename, calc_checksum=False):
    if not os.path.isfile(filename):
        raise FileNotFoundError(f"could not find file {filename}")

    file_ext = os.path.splitext(filename)[1][len(os.path.extsep) :]

    res = {}
    if file_ext in ["yaml", "yml"]:
        with open(filename, "r", encoding="utf-8") as fh:
            content = fh.read()
            res = _load_yaml(content)
    elif file_ext in ["json"]:
        with open(filename, "r", encoding="utf-8") as fh:
            content = fh.read()
            res = _load_json(content)
    else:
        raise NotImplementedError(
            f"markup parsing for extension {file_ext} is not implemented"
        )

    if calc_checksum:
        checksum = _checksum(content.encode())
    else:
        checksum = None
    return res, checksum


def _load_json(data):
    return json.loads(data)


def _load_yaml(data, Loader=SafeLoader):
    return yaml.load(data, Loader=Loader)


def _checksum(data):
    m = hashlib.sha256()
    m.update(data)
    return m.hexdigest()
