#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

EVENT_TYPE = "jpapt.candidate-completed"
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
CANDIDATE_RE = re.compile(r"^candidate-[0-9]{6}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def boolean(value: str, name: str) -> bool:
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise SystemExit(f"{name} must be true or false")


def nullable(value: str) -> str | None:
    return value or None


def derive_conclusion(results: dict[str, str], dry_run: bool) -> tuple[str, list[str]]:
    relevant = {
        name: result
        for name, result in results.items()
        if result and result not in {"skipped", "success"}
    }
    failed_jobs = [f"{name}:{result}" for name, result in relevant.items()]
    if any(result == "failure" for result in relevant.values()):
        return "failure", failed_jobs
    if any(result == "cancelled" for result in relevant.values()):
        return "cancelled", failed_jobs
    if dry_run:
        return "success", failed_jobs
    selected = [
        result
        for name, result in results.items()
        if name in {"github-linux-cpu", "github-linux-cuda", "github-macos-coreml", "github-windows-directml", "hf-jobs"}
        and result != "skipped"
    ]
    if selected == ["success"]:
        return "success", failed_jobs
    return "failure", failed_jobs or ["evaluation:missing-terminal-result"]


def validate(receipt: dict) -> None:
    if receipt.get("schema_version") != 1:
        raise SystemExit("schema_version must be 1")
    for field in ("source_repository", "receipt_repository", "orchestrator_repository"):
        value = receipt.get(field)
        if not isinstance(value, str) or not REPOSITORY_RE.fullmatch(value):
            raise SystemExit(f"{field} must use owner/name")
    request_id = receipt.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise SystemExit("request_id is invalid")
    if receipt.get("conclusion") not in {"success", "failure", "cancelled"}:
        raise SystemExit("conclusion is invalid")
    if not isinstance(receipt.get("dry_run"), bool):
        raise SystemExit("dry_run must be boolean")
    if receipt.get("suite") not in {"smoke", "parity", "probe"}:
        raise SystemExit("suite is invalid")
    if receipt.get("executor") not in {"github", "hf_jobs"}:
        raise SystemExit("executor is invalid")
    if receipt.get("environment") not in {"linux-cpu", "linux-cuda", "macos-coreml", "windows-directml"}:
        raise SystemExit("environment is invalid")
    if receipt.get("workflow_file") != "candidate-package-evaluate-v2.yml":
        raise SystemExit("workflow_file is invalid")
    if not isinstance(receipt.get("run_id"), int) or receipt["run_id"] < 1:
        raise SystemExit("run_id is invalid")
    if not isinstance(receipt.get("run_attempt"), int) or receipt["run_attempt"] < 1:
        raise SystemExit("run_attempt is invalid")
    if not isinstance(receipt.get("run_url"), str) or not receipt["run_url"].startswith("https://"):
        raise SystemExit("run_url is invalid")
    if not isinstance(receipt.get("commit_sha"), str) or not SHA_RE.fullmatch(receipt["commit_sha"]):
        raise SystemExit("commit_sha is invalid")
    requested = receipt.get("requested_candidate_id")
    if requested != "latest" and (not isinstance(requested, str) or not CANDIDATE_RE.fullmatch(requested)):
        raise SystemExit("requested_candidate_id is invalid")
    resolved = receipt.get("resolved_candidate_id")
    if resolved is not None and (not isinstance(resolved, str) or not CANDIDATE_RE.fullmatch(resolved)):
        raise SystemExit("resolved_candidate_id is invalid")
    digest = receipt.get("image_digest")
    if digest is not None and (not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest)):
        raise SystemExit("image_digest is invalid")
    if receipt["conclusion"] == "success" and not receipt["dry_run"]:
        for field in ("resolved_candidate_id", "image_ref", "image_digest", "result_artifact"):
            if not receipt.get(field):
                raise SystemExit(f"successful evaluation receipt requires {field}")
    if not isinstance(receipt.get("failed_jobs"), list) or not all(
        isinstance(item, str) and item for item in receipt["failed_jobs"]
    ):
        raise SystemExit("failed_jobs is invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--dispatch-body", required=True)
    args = parser.parse_args()

    dry_run = boolean(env("DRY_RUN", "false"), "DRY_RUN")
    results = {
        "build": env("BUILD_RESULT"),
        "github-linux-cpu": env("CPU_RESULT"),
        "github-linux-cuda": env("CUDA_RESULT"),
        "github-macos-coreml": env("COREML_RESULT"),
        "github-windows-directml": env("DIRECTML_RESULT"),
        "hf-jobs": env("HF_JOBS_RESULT"),
    }
    conclusion, failed_jobs = derive_conclusion(results, dry_run)

    requested_candidate_id = env("REQUESTED_CANDIDATE_ID") or "latest"
    resolved_candidate_id = env("RESOLVED_CANDIDATE_ID")
    executor = env("EXECUTOR")
    suite = env("SUITE")
    environment = env("ENVIRONMENT")
    result_artifact: str | None = None
    result_uri: str | None = None
    if conclusion == "success" and not dry_run and resolved_candidate_id:
        if executor == "hf_jobs":
            result_artifact = f"candidate-package-{resolved_candidate_id}-hf-jobs-{suite}"
            result_uri = (
                f"hf://buckets/{env('HF_BUCKET')}/runs/hf-jobs/{resolved_candidate_id}/"
                f"{suite}-{env('RUN_ID')}-{env('RUN_ATTEMPT')}/result.json"
            )
        else:
            result_artifact = f"candidate-package-{resolved_candidate_id}-{environment}-{suite}"

    completed_at = env("COMPLETED_AT") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    receipt = {
        "schema_version": 1,
        "request_id": env("REQUEST_ID"),
        "source_repository": env("SOURCE_REPOSITORY"),
        "receipt_repository": env("RECEIPT_REPOSITORY"),
        "conclusion": conclusion,
        "dry_run": dry_run,
        "suite": suite,
        "executor": executor,
        "environment": environment,
        "provider": env("PROVIDER"),
        "orchestrator_repository": env("ORCHESTRATOR_REPOSITORY"),
        "workflow_file": "candidate-package-evaluate-v2.yml",
        "run_id": int(env("RUN_ID")),
        "run_attempt": int(env("RUN_ATTEMPT", "1")),
        "run_url": env("RUN_URL"),
        "commit_sha": env("COMMIT_SHA"),
        "requested_candidate_id": requested_candidate_id,
        "resolved_candidate_id": nullable(resolved_candidate_id),
        "image_ref": nullable(env("IMAGE_REF")),
        "image_digest": nullable(env("IMAGE_DIGEST")),
        "result_artifact": result_artifact,
        "result_uri": result_uri,
        "failed_jobs": failed_jobs,
        "completed_at": completed_at,
    }
    validate(receipt)

    receipt_path = Path(args.receipt)
    dispatch_path = Path(args.dispatch_body)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    dispatch_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    dispatch_path.write_text(
        json.dumps({"event_type": EVENT_TYPE, "client_payload": receipt}, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(receipt_path.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
