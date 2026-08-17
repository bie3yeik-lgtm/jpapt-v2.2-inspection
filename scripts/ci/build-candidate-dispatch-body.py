#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os


def env(name: str) -> str:
    return os.environ.get(name, "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", required=True)
    parser.add_argument("--ref", default="main")
    args = parser.parse_args()

    inputs = {
        "request_id": env("REQUEST_ID"),
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
        "dry_run": False,
    }
    body = {"ref": args.ref, "inputs": inputs}
    compact = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    with open(args.github_output, "a", encoding="utf-8") as handle:
        handle.write(f"body={compact}\n")
    print(json.dumps(body, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
