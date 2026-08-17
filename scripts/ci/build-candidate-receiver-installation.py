#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from candidate_protocol_common import parse_rfc3339_time

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_FIELDS = {
    "schema_version",
    "receiver_repository",
    "orchestrator_repository",
    "orchestrator_commit_sha",
    "managed_files",
    "installed_at",
}


def validate(value: dict) -> None:
    if set(value) != EXPECTED_FIELDS:
        missing = sorted(EXPECTED_FIELDS - set(value))
        unknown = sorted(set(value) - EXPECTED_FIELDS)
        raise SystemExit(f"installation fields mismatch: missing={missing}, unknown={unknown}")
    if value.get("schema_version") != 1:
        raise SystemExit("schema_version must be 1")
    for field in ("receiver_repository", "orchestrator_repository"):
        raw = value.get(field)
        if not isinstance(raw, str) or not REPOSITORY_RE.fullmatch(raw):
            raise SystemExit(f"{field} must use owner/name")
    commit = value.get("orchestrator_commit_sha")
    if not isinstance(commit, str) or not SHA40_RE.fullmatch(commit):
        raise SystemExit("orchestrator_commit_sha must be 40 lowercase hex")
    files = value.get("managed_files")
    if not isinstance(files, list) or not files:
        raise SystemExit("managed_files must be a non-empty list")
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise SystemExit("managed_files entries must contain path and sha256 only")
        path = item["path"]
        digest = item["sha256"]
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts:
            raise SystemExit("managed file path must be repository-relative")
        if path in seen:
            raise SystemExit(f"duplicate managed file path: {path}")
        seen.add(path)
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise SystemExit(f"invalid sha256 for {path}")
    try:
        parse_rfc3339_time(value.get("installed_at"), "installed_at")
    except ValueError as error:
        raise SystemExit(str(error)) from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--validate")
    parser.add_argument("--file", action="append", default=[], metavar="TARGET=SOURCE")
    args = parser.parse_args()

    if args.validate:
        value = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise SystemExit("installation manifest must be a JSON object")
        validate(value)
        return 0

    if not args.output or not args.file:
        parser.error("--output and at least one --file TARGET=SOURCE are required")

    managed_files = []
    for mapping in args.file:
        if "=" not in mapping:
            raise SystemExit(f"invalid --file mapping: {mapping}")
        target, source = mapping.split("=", 1)
        source_path = Path(source)
        if not source_path.is_file():
            raise SystemExit(f"managed source file not found: {source}")
        managed_files.append({
            "path": target,
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        })

    value = {
        "schema_version": 1,
        "receiver_repository": os.environ.get("RECEIVER_REPOSITORY", ""),
        "orchestrator_repository": os.environ.get("ORCHESTRATOR_REPOSITORY", ""),
        "orchestrator_commit_sha": os.environ.get("ORCHESTRATOR_COMMIT_SHA", ""),
        "managed_files": managed_files,
        "installed_at": os.environ.get("INSTALLED_AT")
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    validate(value)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
