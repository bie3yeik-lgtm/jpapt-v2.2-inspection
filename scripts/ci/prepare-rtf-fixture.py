#!/usr/bin/env python3
"""Materialize one immutable RTF fixture for transfer to provider Pods."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

from huggingface_hub import HfHubHTTPError, hf_hub_download


def download(repo_id: str, revision: str, filename: str, cache_dir: Path) -> Path:
    attempts = int(os.environ.get("RTF_HF_429_MAX_ATTEMPTS", "3"))
    wait_seconds = int(os.environ.get("RTF_HF_429_WAIT_SECONDS", "300"))
    for attempt in range(1, attempts + 1):
        try:
            return Path(
                hf_hub_download(
                    repo_id=repo_id,
                    repo_type="dataset",
                    filename=filename,
                    revision=revision,
                    cache_dir=cache_dir,
                    token=os.environ.get("HF_TOKEN"),
                )
            )
        except HfHubHTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status != 429 or attempt >= attempts:
                raise
            print(
                f"HF Hub 429 while materializing {filename}; "
                f"waiting {wait_seconds}s for the five-minute rate window "
                f"(attempt {attempt}/{attempts - 1})",
                flush=True,
            )
            time.sleep(wait_seconds)
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--filename", default="benchmark-v1.jsonl")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    args = parser.parse_args()

    if not os.environ.get("HF_TOKEN"):
        raise SystemExit("HF_TOKEN is required to materialize the RTF fixture")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = args.output_dir.parent / ".rtf-fixture-hf-cache"
    source_manifest = download(args.repo_id, args.revision, args.filename, cache_dir)
    manifest_sha256 = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
    if manifest_sha256 != args.expected_manifest_sha256:
        raise SystemExit(
            f"fixture manifest SHA-256 mismatch: expected {args.expected_manifest_sha256}, "
            f"observed {manifest_sha256}"
        )

    records = []
    for line_number, line in enumerate(source_manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        record = json.loads(line)
        source = str(record["audio_path"])
        local = download(args.repo_id, args.revision, source, cache_dir)
        destination = args.output_dir / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, destination)
        expected_sha256 = record.get("audio_sha256")
        observed_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
        if expected_sha256 and expected_sha256 != observed_sha256:
            raise SystemExit(f"audio SHA-256 mismatch at fixture line {line_number}: {source}")
        records.append(record)

    shutil.copyfile(source_manifest, args.output_dir / args.filename)
    print(
        json.dumps(
            {
                "repo_id": args.repo_id,
                "revision": args.revision,
                "manifest_sha256": manifest_sha256,
                "sample_count": len(records),
                "output_dir": str(args.output_dir),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
