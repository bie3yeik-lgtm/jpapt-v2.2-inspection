#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_CONFIG = Path("config/candidate-receiver-bundle.json")


def relative_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{field} must be a non-empty repository-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"{field} must be repository-relative without traversal: {value}")
    return value


def load_bundle(path: Path, *, verify_sources: bool = True) -> list[dict[str, str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid receiver bundle config {path}: {error}") from error
    if not isinstance(value, dict) or set(value) != {"schema_version", "files"}:
        raise SystemExit("receiver bundle must contain schema_version and files only")
    if value.get("schema_version") != 1:
        raise SystemExit("receiver bundle schema_version must be 1")
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit("receiver bundle files must be a non-empty list")

    result: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict) or set(item) != {"path", "source"}:
            raise SystemExit(f"receiver bundle files[{index}] must contain path and source only")
        target = relative_path(item.get("path"), f"files[{index}].path")
        source = relative_path(item.get("source"), f"files[{index}].source")
        if target in seen_paths:
            raise SystemExit(f"duplicate receiver bundle target path: {target}")
        seen_paths.add(target)
        if verify_sources and not Path(source).is_file():
            raise SystemExit(f"receiver bundle source does not exist: {source}")
        result.append({"path": target, "source": source})
    return result


def installation_paths(manifest_path: Path) -> set[str]:
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid receiver installation manifest {manifest_path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit("receiver installation manifest must be an object")
    managed = value.get("managed_files")
    if not isinstance(managed, list):
        raise SystemExit("receiver installation manifest managed_files must be a list")
    paths: set[str] = set()
    for index, item in enumerate(managed):
        if not isinstance(item, dict):
            raise SystemExit(f"managed_files[{index}] must be an object")
        path = relative_path(item.get("path"), f"managed_files[{index}].path")
        if path in paths:
            raise SystemExit(f"duplicate managed file path in installation: {path}")
        paths.add(path)
    return paths


def assert_installation(bundle: list[dict[str, str]], manifest_path: Path) -> None:
    actual = installation_paths(manifest_path)
    expected = {item["path"] for item in bundle}
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise SystemExit(
            f"receiver installation bundle mismatch: missing={missing}, unexpected={unexpected}"
        )


def obsolete_installation_paths(bundle: list[dict[str, str]], manifest_path: Path) -> list[str]:
    actual = installation_paths(manifest_path)
    expected = {item["path"] for item in bundle}
    return sorted(actual - expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--paths", action="store_true")
    output.add_argument("--mappings", action="store_true")
    output.add_argument("--tsv", action="store_true")
    output.add_argument("--validate", action="store_true")
    output.add_argument("--assert-installation")
    output.add_argument("--obsolete-installation")
    args = parser.parse_args()

    bundle = load_bundle(Path(args.config))
    if args.paths:
        for item in bundle:
            print(item["path"])
    elif args.mappings:
        for item in bundle:
            print(f"{item['path']}={item['source']}")
    elif args.tsv:
        for item in bundle:
            print(f"{item['path']}\t{item['source']}")
    elif args.assert_installation:
        assert_installation(bundle, Path(args.assert_installation))
    elif args.obsolete_installation:
        for path in obsolete_installation_paths(bundle, Path(args.obsolete_installation)):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
