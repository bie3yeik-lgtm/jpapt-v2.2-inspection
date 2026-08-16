#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def parse_bool(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise SystemExit(f"{name} must be boolean")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--github-output", required=True)
    args = parser.parse_args()

    if args.event_name == "repository_dispatch":
        raw = env("PAYLOAD", "{}")
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SystemExit(f"PAYLOAD is invalid JSON: {error}") from error
        if not isinstance(request, dict):
            raise SystemExit("PAYLOAD must be a JSON object")
        execute = parse_bool(request.pop("execute", False), "execute")
    else:
        request = {
            "source_repository": env("I_SOURCE_REPOSITORY"),
            "hf_bucket": env("I_HF_BUCKET"),
            "candidate_id": env("I_CANDIDATE_ID"),
            "package_name": env("I_PACKAGE_NAME"),
            "dataset_source": env("I_DATASET_SOURCE", "auto"),
            "dataset_id": env("I_DATASET_ID"),
            "suite": env("I_SUITE", "smoke"),
            "executor": env("I_EXECUTOR", "github"),
            "environment": env("I_ENVIRONMENT", "linux-cpu"),
            "hf_flavor": env("I_HF_FLAVOR", "cpu-basic"),
            "hf_jobs_image": env("I_HF_JOBS_IMAGE"),
            "dry_run": False,
        }
        execute = parse_bool(env("I_EXECUTE", "false"), "execute")

    source_repository = request.get("source_repository")
    if not isinstance(source_repository, str):
        raise SystemExit("source_repository must be string")

    output = Path(args.output)
    output.write_text(json.dumps(request, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    with open(args.github_output, "a", encoding="utf-8") as handle:
        handle.write(f"execute={str(execute).lower()}\n")
        handle.write(f"source_repository={source_repository}\n")
    print(output.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
