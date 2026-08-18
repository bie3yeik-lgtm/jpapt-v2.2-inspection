#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def invoke_json(command: list[str]) -> dict:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit={completed.returncode}"
        raise RuntimeError(detail)
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("workload helper returned invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("workload helper returned non-object JSON")
    return value


def render_output(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value).replace("\n", " ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--dataset-source", choices=["bucket", "repository", "custom"], required=True)
    parser.add_argument("--dataset-id", default="")
    parser.add_argument("--candidate-id", default="")
    parser.add_argument("--runtime-variant", default="")
    parser.add_argument("--request-json")
    parser.add_argument("--config-json")
    parser.add_argument("--github-output")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    candidate_command = [
        sys.executable,
        str(root / "measure-candidate-bucket-size.py"),
        "--bucket",
        args.bucket,
        "--allow-unavailable",
    ]
    if args.request_json:
        candidate_command.extend(["--request-json", args.request_json])
        if args.config_json:
            candidate_command.extend(["--config-json", args.config_json])
    elif args.candidate_id:
        candidate_command.extend(["--candidate-id", args.candidate_id])
    if args.runtime_variant:
        candidate_command.extend(["--runtime-variant", args.runtime_variant])

    dataset_command = [
        sys.executable,
        str(root / "measure-dataset-source-size.py"),
        "--source",
        args.dataset_source,
        "--allow-unavailable",
    ]
    if args.dataset_source == "bucket":
        dataset_command.extend(["--bucket", args.bucket])
    else:
        dataset_command.extend(["--dataset-id", args.dataset_id])

    candidate = invoke_json(candidate_command)
    dataset = invoke_json(dataset_command)
    result = {
        "schema_version": 1,
        "candidate": candidate,
        "dataset": dataset,
        "fully_available": candidate.get("available") is True and dataset.get("available") is True,
    }

    if args.github_output:
        values = {
            "candidate_available": candidate.get("available"),
            "candidate_id": candidate.get("candidate_id"),
            "candidate_bytes": candidate.get("candidate_bytes"),
            "candidate_files": candidate.get("candidate_files"),
            "candidate_legacy_layout": candidate.get("legacy_candidate_layout"),
            "candidate_warning": candidate.get("warning"),
            "dataset_available": dataset.get("available"),
            "dataset_source": dataset.get("dataset_source"),
            "dataset_id": dataset.get("dataset_id"),
            "dataset_bytes": dataset.get("dataset_bytes"),
            "dataset_files": dataset.get("dataset_files"),
            "dataset_probe_method": dataset.get("probe_method"),
            "dataset_warning": dataset.get("warning"),
            "fully_available": result["fully_available"],
        }
        with open(args.github_output, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={render_output(value)}\n")

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
