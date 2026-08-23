#!/usr/bin/env python3
"""Bind RunPod billing history to an immutable RTF result."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, hf_hub_url

RUNPOD_BILLING_URL = "https://rest.runpod.io/v1/billing/pods"


def _positive_number(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _request_json(url: str, token: str) -> Any:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def fetch_billing_history(pod_id: str, token: str, *, attempts: int = 6) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"podId": pod_id, "grouping": "podId", "bucketSize": "hour"})
    url = f"{RUNPOD_BILLING_URL}?{query}"
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            payload = _request_json(url, token)
            if not isinstance(payload, list):
                raise ValueError("RunPod billing response is not a list")
            records = [
                item
                for item in payload
                if isinstance(item, dict) and item.get("podId") == pod_id
            ]
            if records:
                return records
        except Exception as error:  # noqa: BLE001 - retry provider eventual consistency
            last_error = error
        if attempt + 1 < attempts:
            time.sleep(10)
    if last_error is not None:
        raise RuntimeError(f"RunPod billing history unavailable: {last_error}") from last_error
    raise RuntimeError(f"RunPod billing history has no record for Pod {pod_id}")


def build_billing_metadata(pod_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    amount = sum(_positive_number(item.get("amount"), "billing amount") for item in records)
    billed_ms = sum(int(item.get("timeBilledMs", 0)) for item in records)
    if billed_ms <= 0:
        raise ValueError("RunPod billing history has no positive timeBilledMs")
    gpu_types = {item.get("gpuTypeId") for item in records if item.get("gpuTypeId")}
    if len(gpu_types) != 1:
        raise ValueError("RunPod billing history has no unique gpuTypeId")
    billed_seconds = billed_ms // 1000
    if billed_seconds <= 0:
        raise ValueError("RunPod billing history duration is below one second")
    return {
        "provider": "runpod-pod",
        "job_id": pod_id,
        "url": f"https://console.runpod.io/pods/{pod_id}",
        "gpu_type_id": next(iter(gpu_types)),
        "billing_duration_sec": billed_ms / 1000.0,
        "billed_seconds": billed_seconds,
        "job_cost_usd": amount,
        "cost_basis": "runpod_billing_history",
    }


def _download_metrics(uri: str, token: str) -> bytes:
    request = urllib.request.Request(uri, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    runpod_token = os.environ.get("RUNPOD_TOKEN") or os.environ.get("RUNPOD_API")
    hf_token = os.environ.get("HF_TOKEN")
    if not runpod_token:
        raise SystemExit("RUNPOD_TOKEN is required for RunPod billing metadata collection")
    if not hf_token:
        raise SystemExit("HF_TOKEN is required to update the HF Dataset metrics result")

    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    if receipt.get("status") != "completed":
        return 0
    pod_id = receipt.get("job_id")
    metrics_uri = receipt.get("metrics_uri")
    repo_id = receipt.get("result_repo_id")
    path_in_repo = receipt.get("result_path")
    if not all(isinstance(value, str) and value for value in (pod_id, metrics_uri, repo_id, path_in_repo)):
        raise SystemExit("completed RunPod receipt is missing Pod, metrics, or result repository identity")

    records = fetch_billing_history(pod_id, runpod_token)
    metadata = build_billing_metadata(pod_id, records)
    original = _download_metrics(metrics_uri, hf_token)
    if hashlib.sha256(original).hexdigest() != receipt.get("metrics_sha256"):
        raise SystemExit("source RunPod metrics SHA-256 does not match receipt")
    payload = json.loads(original)
    audio_hours = _positive_number(payload.get("audio_duration_sec"), "audio_duration_sec") / 3600.0
    payload["provider_job"] = metadata
    payload["cost_per_audio_hour"] = metadata["job_cost_usd"] / audio_hours
    if payload.get("gpu_price_per_hour") is None:
        payload["gpu_price_per_hour"] = metadata["job_cost_usd"] / (metadata["billing_duration_sec"] / 3600.0)
    enriched = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    api = HfApi(token=hf_token)
    commit = api.upload_file(
        path_or_fileobj=enriched,
        path_in_repo=path_in_repo,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Bind RunPod billing metadata {payload['run_id']}",
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
