#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Protocol

BUCKET_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CANDIDATE_RE = re.compile(r"^candidate-[0-9]{6}$")


class BucketItemLike(Protocol):
    path: str
    type: str
    size: int


def candidate_files(
    items: Iterable[BucketItemLike], relative_path: str
) -> list[BucketItemLike]:
    prefix = relative_path.rstrip("/") + "/"
    selected: list[BucketItemLike] = []
    for item in items:
        if getattr(item, "type", None) != "file":
            continue
        path = getattr(item, "path", None)
        size = getattr(item, "size", None)
        if not isinstance(path, str) or not isinstance(size, int) or size < 0:
            continue
        normalized = path.removeprefix("candidates/")
        if normalized.startswith(prefix):
            selected.append(item)
    return selected


def parse_resolver_output(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    candidate_id = values.get("candidate_id", "")
    relative_path = values.get("relative_path", "")
    legacy = values.get("legacy", "")
    if not CANDIDATE_RE.fullmatch(candidate_id):
        raise ValueError("candidate resolver returned invalid candidate_id")
    if not relative_path or relative_path.startswith("/") or ".." in Path(relative_path).parts:
        raise ValueError("candidate resolver returned invalid relative_path")
    if legacy not in {"true", "false"}:
        raise ValueError("candidate resolver returned invalid legacy flag")
    return {
        "candidate_id": candidate_id,
        "relative_path": relative_path,
        "legacy": legacy,
    }


def resolve_candidate(
    listing: Path,
    *,
    candidate_id: str,
    runtime_variant: str,
) -> dict[str, str]:
    command = [
        "cargo",
        "run",
        "--quiet",
        "--locked",
        "-p",
        "asr-hf",
        "--",
        "resolve-candidate-location",
        "--listing",
        str(listing),
    ]
    if candidate_id and candidate_id != "latest":
        command.extend(["--candidate-id", candidate_id])
    if runtime_variant:
        command.extend(["--runtime-variant", runtime_variant])
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return parse_resolver_output(completed.stdout)


def write_github_output(path: str | None, result: dict) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key in (
            "available",
            "candidate_id",
            "candidate_relative_path",
            "candidate_bytes",
            "candidate_files",
            "legacy_candidate_layout",
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


def unavailable(message: str) -> dict:
    return {
        "schema_version": 1,
        "available": False,
        "candidate_id": None,
        "candidate_relative_path": None,
        "candidate_bytes": None,
        "candidate_files": None,
        "legacy_candidate_layout": None,
        "warning": message,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--candidate-id", default="")
    parser.add_argument("--runtime-variant", default="")
    parser.add_argument("--github-output")
    parser.add_argument("--allow-unavailable", action="store_true")
    args = parser.parse_args()

    if not BUCKET_RE.fullmatch(args.bucket):
        raise SystemExit("bucket must use namespace/name")
    if args.candidate_id not in {"", "latest"} and not CANDIDATE_RE.fullmatch(args.candidate_id):
        raise SystemExit("candidate_id must be candidate-NNNNNN, latest, or blank")

    token = os.environ.get("HF_TOKEN") or None
    try:
        from huggingface_hub import list_bucket_tree

        items = list(
            list_bucket_tree(
                args.bucket,
                prefix="candidates",
                recursive=True,
                token=token,
            )
        )
        file_paths = sorted(
            item.path
            for item in items
            if getattr(item, "type", None) == "file"
            and isinstance(getattr(item, "path", None), str)
        )
        if not file_paths:
            raise RuntimeError("candidate collection contains no files")

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            listing = Path(handle.name)
            for path in file_paths:
                handle.write(path + "\n")
        try:
            resolved = resolve_candidate(
                listing,
                candidate_id=args.candidate_id,
                runtime_variant=args.runtime_variant,
            )
        finally:
            listing.unlink(missing_ok=True)

        files = candidate_files(items, resolved["relative_path"])
        if not files:
            raise RuntimeError("resolved candidate contains no file metadata")
        total_bytes = sum(int(item.size) for item in files)
        result = {
            "schema_version": 1,
            "available": True,
            "candidate_id": resolved["candidate_id"],
            "candidate_relative_path": resolved["relative_path"],
            "candidate_bytes": total_bytes,
            "candidate_files": len(files),
            "legacy_candidate_layout": resolved["legacy"] == "true",
            "warning": None,
        }
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        if not args.allow_unavailable:
            raise SystemExit(f"candidate workload probe failed: {error}") from error
        result = unavailable(str(error))
        print(f"::warning::candidate workload probe unavailable: {error}", file=sys.stderr)

    write_github_output(args.github_output, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
