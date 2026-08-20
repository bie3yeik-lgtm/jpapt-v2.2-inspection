#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re

from huggingface_hub import list_bucket_tree

BUCKET_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def validate_bucket_id(value: str) -> str:
    if not BUCKET_RE.fullmatch(value):
        raise SystemExit(f"bucket must use namespace/name: {value}")
    owner, name = value.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise SystemExit(f"bucket must not contain dot-only path segments: {value}")
    return value


def validate_object_path(value: str) -> str:
    if not value or value.startswith("/") or value.endswith("/"):
        raise SystemExit(f"bucket object path is invalid: {value}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SystemExit(f"bucket object path contains an unsafe path segment: {value}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    bucket = validate_bucket_id(args.bucket)
    object_path = validate_object_path(args.path)
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        raise SystemExit("HF_TOKEN is required for Bucket object lookup")

    found = False
    try:
        for item in list_bucket_tree(
            bucket_id=bucket,
            prefix=object_path,
            recursive=True,
            token=token,
        ):
            if getattr(item, "path", None) != object_path:
                continue
            if getattr(item, "type", None) != "file":
                raise RuntimeError(f"expected Bucket object path to be a file: {object_path}")
            found = True
            break
    except Exception as error:
        raise SystemExit(f"Bucket object lookup failed for {bucket}/{object_path}: {error}") from error

    print("true" if found else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
