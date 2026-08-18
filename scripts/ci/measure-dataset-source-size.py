#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Iterable, Protocol

BUCKET_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class SizedItemLike(Protocol):
    path: str
    size: int


def sized_files(items: Iterable[SizedItemLike]) -> list[SizedItemLike]:
    selected: list[SizedItemLike] = []
    for item in items:
        path = getattr(item, "path", None)
        size = getattr(item, "size", None)
        item_type = getattr(item, "type", "file")
        if item_type != "file":
            continue
        if not isinstance(path, str) or not path:
            continue
        if not isinstance(size, int) or size < 0:
            continue
        selected.append(item)
    return selected


def unavailable(source: str, dataset_id: str | None, message: str) -> dict:
    return {
        "schema_version": 1,
        "available": False,
        "dataset_source": source,
        "dataset_id": dataset_id,
        "dataset_bytes": None,
        "dataset_files": None,
        "probe_method": "unavailable",
        "warning": message,
    }


def emit(result: dict, github_output: str | None) -> None:
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            for key in (
                "available",
                "dataset_source",
                "dataset_id",
                "dataset_bytes",
                "dataset_files",
                "probe_method",
                "warning",
            ):
                value = result.get(key)
                if isinstance(value, bool):
                    rendered = "true" if value else "false"
                elif value is None:
                    rendered = ""
                else:
                    rendered = str(value).replace("\n", " ")
                handle.write(f"{key}={rendered}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def fail_or_unavailable(
    *,
    source: str,
    dataset_id: str | None,
    error: Exception,
    allow_unavailable: bool,
) -> dict:
    if not allow_unavailable:
        raise SystemExit(f"dataset workload probe failed: {error}") from error
    print(f"::warning::dataset workload probe unavailable: {error}", file=sys.stderr)
    return unavailable(source, dataset_id, str(error))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["bucket", "repository", "custom"], required=True)
    parser.add_argument("--bucket", default="")
    parser.add_argument("--dataset-id", default="")
    parser.add_argument("--github-output")
    parser.add_argument("--allow-unavailable", action="store_true")
    args = parser.parse_args()

    if args.source == "bucket":
        if not BUCKET_RE.fullmatch(args.bucket):
            raise SystemExit("bucket dataset source requires --bucket namespace/name")
        if args.dataset_id:
            raise SystemExit("bucket dataset source does not accept --dataset-id")
    else:
        if not REPO_RE.fullmatch(args.dataset_id):
            raise SystemExit(f"{args.source} dataset source requires --dataset-id owner/name")

    token = os.environ.get("HF_TOKEN") or None
    try:
        if args.source == "bucket":
            from huggingface_hub import list_bucket_tree

            items = list(
                list_bucket_tree(
                    args.bucket,
                    prefix="datasets",
                    recursive=True,
                    token=token,
                )
            )
            method = "bucket-metadata"
            resolved_dataset_id: str | None = None
        else:
            from huggingface_hub import list_repo_tree

            items = list(
                list_repo_tree(
                    args.dataset_id,
                    repo_type="dataset",
                    recursive=True,
                    token=token,
                )
            )
            method = "dataset-repo-metadata"
            resolved_dataset_id = args.dataset_id
    except Exception as error:  # HF client/network/auth boundary.
        result = fail_or_unavailable(
            source=args.source,
            dataset_id=args.dataset_id or None,
            error=error,
            allow_unavailable=args.allow_unavailable,
        )
        emit(result, args.github_output)
        return 0

    files = sized_files(items)
    if not files:
        result = fail_or_unavailable(
            source=args.source,
            dataset_id=resolved_dataset_id,
            error=RuntimeError("dataset source contains no file metadata"),
            allow_unavailable=args.allow_unavailable,
        )
        emit(result, args.github_output)
        return 0
    total_bytes = sum(int(item.size) for item in files)
    if total_bytes <= 0:
        result = fail_or_unavailable(
            source=args.source,
            dataset_id=resolved_dataset_id,
            error=RuntimeError("dataset source has no positive byte metadata"),
            allow_unavailable=args.allow_unavailable,
        )
        emit(result, args.github_output)
        return 0

    result = {
        "schema_version": 1,
        "available": True,
        "dataset_source": args.source,
        "dataset_id": resolved_dataset_id,
        "dataset_bytes": total_bytes,
        "dataset_files": len(files),
        "probe_method": method,
        "warning": None,
    }
    emit(result, args.github_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
