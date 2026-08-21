from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, hf_hub_url


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is required to publish the benchmark result")
    return value


def _write_receipt(receipt: dict[str, Any]) -> None:
    receipt_path = Path(os.environ.get("RTF_RECEIPT", "/output/result-receipt.json"))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RTF_RESULT_RECEIPT=" + json.dumps(receipt, sort_keys=True), flush=True)


def main() -> int:
    output = Path(os.environ.get("RTF_OUTPUT", "/output/metrics.json"))
    if not output.is_file():
        run_id = _required("RTF_RUN_ID")
        receipt = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "blocked",
            "job_id": os.environ.get("JOB_ID") or os.environ.get("RTF_JOB_ID") or None,
            "result_uri": None,
            "result_sha256": None,
            "metrics_uri": None,
            "metrics_sha256": None,
            "error_code": os.environ.get("RTF_FAILURE_CODE", "BENCHMARK_INFERENCE_FAILED"),
            "error_message": os.environ.get(
                "RTF_FAILURE_MESSAGE", f"metrics output does not exist: {output}"
            ),
        }
        _write_receipt(receipt)
        return 0

    run_id = _required("RTF_RUN_ID")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if payload.get("run_id") != run_id:
        raise RuntimeError("metrics run_id does not match RTF_RUN_ID")
    payload_status = payload.get("status", "blocked")
    if payload_status != "completed":
        receipt: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "status": payload_status,
            "job_id": os.environ.get("JOB_ID") or os.environ.get("RTF_JOB_ID") or None,
            "result_uri": None,
            "result_sha256": None,
            "metrics_uri": None,
            "metrics_sha256": None,
            "error_code": payload.get("error_code", "BENCHMARK_INFERENCE_FAILED"),
            "error_message": payload.get("error_message", "benchmark did not complete"),
        }
        _write_receipt(receipt)
        return 0

    repo_id = _required("RTF_RESULT_REPO_ID")
    path_in_repo = os.environ.get("RTF_RESULT_PATH", f"results/{run_id}/metrics.json")
    if Path(path_in_repo).is_absolute() or ".." in Path(path_in_repo).parts:
        raise RuntimeError("RTF_RESULT_PATH must be a repository-relative path")

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    api = HfApi(token=_required("HF_TOKEN"))
    commit = api.upload_file(
        path_or_fileobj=str(output),
        path_in_repo=path_in_repo,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Publish RTF metrics {run_id}",
    )
    revision = commit.oid
    uri = hf_hub_url(repo_id, filename=path_in_repo, repo_type="dataset", revision=revision)
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "status": payload_status,
        "job_id": os.environ.get("JOB_ID") or os.environ.get("RTF_JOB_ID") or None,
        "result_uri": uri,
        "result_sha256": digest,
        "metrics_uri": uri,
        "metrics_sha256": digest,
        "result_repo_id": repo_id,
        "result_revision": revision,
        "result_path": path_in_repo,
    }
    _write_receipt(receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
