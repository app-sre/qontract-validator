import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import click

from validator.bundle import Bundle
from validator.postprocess import postprocess_bundle
from validator.utils import (
    SUPPORTED_EXTENSIONS,
    FileType,
    get_checksum,
    get_file_type,
    parse_anymarkup_file,
)

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.WARNING)

# regex to get the schema from the resource files.
# we use multiline as we have a raw string with newlines characters
# we don't use pyyaml to parse it as they are jinja templates in most cases
SCHEMA_RE = re.compile(r"^\$schema: (?P<schema>.+\.ya?ml)$", re.MULTILINE)

CHECKSUM_SCHEMA_FIELD = "$file_sha256sum"


@dataclass(frozen=True)
class Spec:
    work_dir: Path
    root: Path
    name: str
    checksum_field_name: str | None = None


def build_content(
    content: dict,
    checksum_field_name: str | None = None,
    checksum: str | None = None,
) -> dict:
    if checksum_field_name:
        content[checksum_field_name] = checksum
    return content


def bundle_datafiles(
    data_dir: Path,
    thread_pool_size: int,
    checksum_field_name: str | None = None,
) -> dict[str, dict]:
    specs = init_specs(data_dir, checksum_field_name)
    with ThreadPoolExecutor(max_workers=thread_pool_size) as pool:
        return {
            path: build_content(content, checksum_field_name, checksum)
            for path, content, checksum in pool.map(bundle_datafile_spec, specs)
            if path is not None and content is not None
        }


def bundle_datafile_spec(spec: Spec) -> tuple[str | None, dict | None, str | None]:
    path = spec.root / spec.name
    if path.suffix not in SUPPORTED_EXTENSIONS:
        return None, None, None
    rel_abs_path = path.as_posix().removeprefix(spec.work_dir.as_posix())
    logging.info("Processing: %s\n", rel_abs_path)
    content, checksum = parse_anymarkup_file(path, spec.checksum_field_name)
    return rel_abs_path, content, checksum


def bundle_resources(resource_dir, thread_pool_size):
    specs = init_specs(resource_dir)
    with ThreadPoolExecutor(max_workers=thread_pool_size) as pool:
        return dict(pool.map(bundle_resource_spec, specs))


def get_schema_from_resource(path: Path, content: str) -> str | None:
    if get_file_type(path) != FileType.YAML:
        return None
    if s := SCHEMA_RE.search(content):
        return s.group("schema")
    return None


def bundle_resource_spec(spec: Spec) -> tuple[str, dict]:
    path = spec.root / spec.name
    rel_abs_path = path.as_posix().removeprefix(spec.work_dir.as_posix())

    logging.info("Resource: %s\n", rel_abs_path)
    data = path.read_bytes()
    content = data.decode("utf-8")
    schema = get_schema_from_resource(path, content)
    sha256sum = get_checksum(data)
    return rel_abs_path, {
        "path": rel_abs_path,
        "content": content,
        "$schema": schema,
        "sha256sum": sha256sum,
        "backrefs": [],
    }


def init_specs(
    work_dir: Path,
    checksum_field_name: str | None = None,
) -> list[Spec]:
    return [
        Spec(
            work_dir=work_dir,
            root=root,
            name=name,
            checksum_field_name=checksum_field_name,
        )
        for root, _, files in work_dir.walk(top_down=False)
        for name in files
        if not name.startswith(".")
    ]


def bundle_graphql(graphql_schema_file: Path):
    if not graphql_schema_file.is_file():
        msg = f"could not find file {graphql_schema_file}"
        raise FileNotFoundError(msg)
    content, _ = parse_anymarkup_file(graphql_schema_file)
    return content


@click.command()
@click.option(
    "--thread-pool-size", default=10, help="number of threads to run in parallel."
)
@click.argument("schema-dir", type=click.Path(exists=True))
@click.argument("graphql-schema-file", type=click.Path(exists=True))
@click.argument("data-dir", type=click.Path(exists=True))
@click.argument("resource-dir", type=click.Path(exists=True))
@click.argument("git-commit")
@click.argument("git-commit-timestamp")
def main(
    thread_pool_size,
    schema_dir,
    graphql_schema_file,
    data_dir,
    resource_dir,
    git_commit,
    git_commit_timestamp,
):
    bundle = Bundle(
        git_commit=git_commit,
        git_commit_timestamp=git_commit_timestamp,
        schemas=bundle_datafiles(Path(schema_dir), thread_pool_size),
        graphql=bundle_graphql(Path(graphql_schema_file)),
        data=bundle_datafiles(
            Path(data_dir), thread_pool_size, checksum_field_name=CHECKSUM_SCHEMA_FIELD
        ),
        resources=bundle_resources(Path(resource_dir), thread_pool_size),
    )

    postprocess_bundle(bundle, checksum_field_name=CHECKSUM_SCHEMA_FIELD)

    sys.stdout.write(json.dumps(asdict(bundle), separators=(",", ":")) + "\n")
