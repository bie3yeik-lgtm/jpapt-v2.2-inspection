#!/usr/bin/env python3
"""Bind Hugging Face Jobs billing metadata to an immutable RTF result."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, hf_hub_url
from huggingface_hub.utils import get_token

JOB_URL = re.compile(r"^https://huggingface\.co/jobs/([^/]+)/([0-9a-f]{24})$")


def _positive_number(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _job_field(job: Any, name: str) -> Any:
    value = getattr(job, name, None)
    if value is None and isinstance(job, dict):
        value = job.get(name)
    return value


def _duration_field(job: Any, name: str) -> float | None:
    durations = _job_field(job, "durations")
    value = getattr(durations, name, None) if durations is not None else None
    if value is None and isinstance(durations, dict):
        value = durations.get(name)
    if value is None:
        return None
    return _positive_number(value, name)


def build_billing_metadata(job: Any, hardware: list[Any], *, job_id: str, namespace: str) -> dict[str, Any]:
    flavor = _job_field(job, "flavor")
    if not isinstance(flavor, str) or not flavor:
        raise ValueError("HF Job metadata does not contain a flavor")
    hardware_by_name = {getattr(item, "name", None): item for item in hardware}
    selected = hardware_by_name.get(flavor)
    unit_cost = getattr(selected, "unit_cost_usd", None) if selected is not None else None
    unit_label = getattr(selected, "unit_label", None) if selected is not None else None
    if unit_cost is None or unit_label != "minute":
        raise ValueError(f"HF hardware pricing is unavailable for flavor {flavor!r}")
    unit_cost = _positive_number(unit_cost, "unit_cost_usd")

    durations = _job_field(job, "durations")
    total_seconds = getattr(durations, "total_secs", None) if durations is not None else None
    if total_seconds is None and isinstance(durations, dict):
        total_seconds = durations.get("total_secs")
    total_seconds = _positive_number(total_seconds, "total_secs")
    billed_minutes = int(math.ceil(total_seconds / 60.0))
    job_cost = billed_minutes * unit_cost

    url = _job_field(job, "url")
    if not isinstance(url, str) or not JOB_URL.fullmatch(url):
        url = f"https://huggingface.co/jobs/{namespace}/{job_id}"
    return {
        "provider": "hf-jobs",
        "job_id": job_id,
        "url": url,
        "namespace": namespace,
        "flavor": flavor,
        "billing_duration_sec": total_seconds,
        "billed_minutes": billed_minutes,
        "unit_cost_usd_per_minute": unit_cost,
        "job_cost_usd": job_cost,
        "cost_basis": "hf_jobs_billed_starting_running_minutes",
    }


def _download_metrics(uri: str, token: str) -> bytes:
    request = urllib.request.Request(uri, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--namespace", default=os.environ.get("HF_JOB_NAMESPACE", "gawohok7"))
    args = parser.parse_args()
    token = get_token()
    if not token:
        raise SystemExit("HF_TOKEN is required for HF Job metadata collection")

    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    if receipt.get("status") != "completed":
        return 0
    job_id = receipt.get("job_id")
    metrics_uri = receipt.get("metrics_uri")
    if not isinstance(job_id, str) or not job_id:
        raise SystemExit("completed HF receipt is missing job_id")
    if not isinstance(metrics_uri, str) or not metrics_uri:
        raise SystemExit("completed HF receipt is missing metrics_uri")
    repo_id = receipt.get("result_repo_id")
    path_in_repo = receipt.get("result_path")
    if not isinstance(repo_id, str) or not isinstance(path_in_repo, str):
        raise SystemExit("completed HF receipt is missing result repository identity")

    api = HfApi(token=token)
    job = api.inspect_job(job_id=job_id, namespace=args.namespace)
    if getattr(getattr(job, "status", None), "stage", None) != "COMPLETED":
        raise SystemExit("HF Job metadata is not in COMPLETED state")
    metadata = build_billing_metadata(
        job,
        list(api.list_jobs_hardware()),
        job_id=job_id,
        namespace=args.namespace,
    )
    original = _download_metrics(metrics_uri, token)
    expected_sha = receipt.get("metrics_sha256")
    if hashlib.sha256(original).hexdigest() != expected_sha:
        raise SystemExit("source HF metrics SHA-256 does not match receipt")
    payload = json.loads(original)
    audio_hours = _positive_number(payload.get("audio_duration_sec"), "audio_duration_sec") / 3600.0
    payload["provider_job"] = metadata
    scheduling_seconds = _duration_field(job, "scheduling_secs")
    if scheduling_seconds is not None:
        payload["queue_latency_sec"] = scheduling_seconds
    payload["gpu_price_per_hour"] = metadata["unit_cost_usd_per_minute"] * 60.0
    payload["cost_per_audio_hour"] = metadata["job_cost_usd"] / audio_hours
    enriched = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    commit = api.upload_file(
        path_or_fileobj=enriched,
        path_in_repo=path_in_repo,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Bind HF Job billing metadata {payload['run_id']}",
    )
    revision = commit.oid
    uri = hf_hub_url(repo_id, filename=path_in_repo, repo_type="dataset", revision=revision)
    digest = hashlib.sha256(enriched).hexdigest()
    receipt.update(
        {
            "result_revision": revision,
            "result_uri": uri,
            "result_sha256": digest,
            "metrics_uri": uri,
            "metrics_sha256": digest,
            "provider_job": metadata,
        }
    )
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, sort_keys=True), flush=True)
    print("RTF_RESULT_RECEIPT=" + json.dumps(receipt, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
