import json
import os
import yaml

try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader as SafeLoader


def parse_anymarkup_file(filename):
    if not os.path.isfile(filename):
        raise FileNotFoundError(f'could not find file {filename}')

    file_ext = os.path.splitext(filename)[1][len(os.path.extsep):]

    res = {}
    if file_ext in ['yaml', 'yml']:
        fh = open(filename, "r", encoding="utf-8")
        res = _load_yaml(fh)
    elif file_ext in ['json']:
        fh = open(filename, "r", encoding="utf-8")
        res = _load_json(fh)
    else:
        raise NotImplementedError(
            f'markup parsing for extension {file_ext} is not implemented')

    return res


def _load_json(fh):
    return json.load(fh)


def _load_yaml(fh, Loader=SafeLoader):
    return yaml.load(fh, Loader=Loader)
