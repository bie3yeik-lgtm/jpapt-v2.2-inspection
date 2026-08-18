#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Protocol

BUCKET_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
KEY_RE = re.compile(r"^[0-9a-f]{24}$")


class BucketItemLike(Protocol):
    path: str
    type: str


def select_lifecycle_events(items: Iterable[BucketItemLike]) -> list[BucketItemLike]:
    selected = [
        item
        for item in items
        if getattr(item, "type", None) == "file"
        and isinstance(getattr(item, "path", None), str)
        and item.path.endswith(".lifecycle.json")
    ]
    return sorted(selected, key=lambda item: item.path)


def collect(
    *,
    bucket: str,
    request_key: str,
    execution_key: str | None,
    output_dir: Path,
    manifest: Path,
    token: str,
    allow_unavailable: bool,
) -> int:
    if not BUCKET_RE.fullmatch(bucket):
        raise SystemExit("bucket must use namespace/name")
    if not KEY_RE.fullmatch(request_key):
        raise SystemExit("request_key must be 24 lowercase hex characters")
    if execution_key is not None and not KEY_RE.fullmatch(execution_key):
        raise SystemExit("execution_key must be 24 lowercase hex characters")
    if not token:
        raise SystemExit("HF_TOKEN is required")

    from huggingface_hub import download_bucket_files, list_bucket_tree

    if execution_key:
        prefix = f"requests/{request_key}/executions/{execution_key}/events"
    else:
        prefix = f"requests/{request_key}/events"
    try:
        items = select_lifecycle_events(
            list_bucket_tree(
                bucket,
                prefix=prefix,
                recursive=True,
                token=token,
            )
        )
    except Exception as error:
        if not allow_unavailable:
            raise
        print(
            f"::warning::persistent lifecycle history unavailable for {bucket}/{prefix}: {error}",
            file=sys.stderr,
        )
        items = []

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    downloads: list[tuple[BucketItemLike, str]] = []
    rows: list[tuple[str, Path]] = []
    for index, item in enumerate(items):
        local = output_dir / f"{index:06d}-{Path(item.path).name}"
        downloads.append((item, str(local)))
        rows.append((item.path, local))

    if downloads:
        download_bucket_files(bucket, files=downloads, token=token)

    with manifest.open("w", encoding="utf-8") as handle:
        for remote, local in rows:
            handle.write(f"{remote}\t{local}\n")

    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--request-key", required=True)
    parser.add_argument("--execution-key")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--allow-unavailable", action="store_true")
    parser.add_argument("--github-output")
    args = parser.parse_args()

    count = collect(
        bucket=args.bucket,
        request_key=args.request_key,
        execution_key=args.execution_key,
        output_dir=Path(args.output_dir),
        manifest=Path(args.manifest),
        token=os.environ.get("HF_TOKEN", ""),
        allow_unavailable=args.allow_unavailable,
    )
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write(f"count={count}\n")
    print(count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
