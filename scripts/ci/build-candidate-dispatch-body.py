#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def env(name: str) -> str:
    return os.environ.get(name, "")


def parse_bool(raw: object, name: str, default: bool = False) -> bool:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.lower() == "true":
        return True
    if isinstance(raw, str) and raw.lower() == "false":
        return False
    raise SystemExit(f"{name} must be true or false")


def resolved_dry_run() -> bool:
    explicit = env("DRY_RUN")
    if explicit != "":
        return parse_bool(explicit, "DRY_RUN")

    request_path = Path(env("REQUEST_JSON") or "/tmp/request.json")
    if request_path.is_file():
        value = json.loads(request_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise SystemExit(f"{request_path} must contain a JSON object")
        return parse_bool(value.get("dry_run"), "request dry_run")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", required=True)
    parser.add_argument("--ref", default="main")
    args = parser.parse_args()

    inputs = {
        "request_id": env("REQUEST_ID"),
        "request_execution_id": env("REQUEST_EXECUTION_ID"),
        "source_repository": env("SOURCE_REPOSITORY"),
        "receipt_repository": env("RECEIPT_REPOSITORY"),
        "hf_bucket": env("HF_BUCKET"),
        "candidate_id": env("CANDIDATE_ID"),
        "package_name": env("PACKAGE_NAME"),
        "dataset_source": env("DATASET_SOURCE"),
        "dataset_id": env("DATASET_ID"),
        "suite": env("SUITE"),
        "executor": env("EXECUTOR"),
        "environment": env("ENVIRONMENT"),
        "hf_flavor": env("HF_FLAVOR"),
        "hf_jobs_image": env("HF_JOBS_IMAGE"),
        "dry_run": resolved_dry_run(),
    }
    body = {"ref": args.ref, "inputs": inputs}
    compact = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    with open(args.github_output, "a", encoding="utf-8") as handle:
        handle.write(f"body={compact}\n")
    print(json.dumps(body, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
