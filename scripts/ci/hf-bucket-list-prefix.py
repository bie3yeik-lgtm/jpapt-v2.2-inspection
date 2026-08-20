#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re

from huggingface_hub import list_bucket_tree

BUCKET_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PREFIX_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_bucket_id(value: str) -> str:
    if not BUCKET_RE.fullmatch(value):
        raise SystemExit(f"bucket must use namespace/name: {value}")
    owner, name = value.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise SystemExit(f"bucket must not contain dot-only path segments: {value}")
    return value


def validate_prefix(value: str) -> str:
    if not value or value.startswith("/") or value.endswith("/"):
        raise SystemExit(f"bucket prefix is invalid: {value}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} or PREFIX_SEGMENT_RE.fullmatch(part) is None for part in parts):
        raise SystemExit(f"bucket prefix contains an unsafe path segment: {value}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()

    bucket = validate_bucket_id(args.bucket)
    prefix = validate_prefix(args.prefix)
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        raise SystemExit("HF_TOKEN is required for Bucket prefix listing")

    try:
        for item in list_bucket_tree(
            bucket_id=bucket,
            prefix=prefix,
            recursive=True,
            token=token,
        ):
            path = getattr(item, "path", None)
            if isinstance(path, str) and path:
                print(path)
    except Exception as error:
        raise SystemExit(f"Bucket prefix listing failed for {bucket}/{prefix}: {error}") from error

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
