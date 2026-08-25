#!/usr/bin/env python3
"""Bind RunPod billing history to an immutable RTF result."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from huggingface_hub import HfApi, hf_hub_url

RUNPOD_BILLING_URL = "https://rest.runpod.io/v1/billing/pods"
# RTX 2000 Ada smoke (Actions run 32871433137):
# - guarded batch 1 pod runtime ~3m
# - full-matrix batch 1->8->32 wall clock ~46m; batch-32 pod ~31m
# RunPod bills on ~5m cycles. Defaults are selected from RTF_COST_MODE.
OBSERVED_RTX2000_ADA_GUARDED_BATCH_SECONDS = 3 * 60
OBSERVED_RTX2000_ADA_FULL_MATRIX_SECONDS = 46 * 60
RUNPOD_BILLING_CYCLE_SECONDS = 5 * 60
GUARDED_BILLING_RETRY_MARGIN_SECONDS = 10 * 60
FULL_MATRIX_BILLING_RETRY_MARGIN_SECONDS = 20 * 60
DEFAULT_BILLING_RETRY_SECONDS = 15.0


def default_billing_max_wait_seconds(*, cost_mode: str | None = None) -> float:
    mode = cost_mode if cost_mode is not None else os.environ.get("RTF_COST_MODE", "guarded")
    if mode == "full-matrix":
        return float(
            OBSERVED_RTX2000_ADA_FULL_MATRIX_SECONDS
            + RUNPOD_BILLING_CYCLE_SECONDS
            + FULL_MATRIX_BILLING_RETRY_MARGIN_SECONDS
        )
    return float(
        OBSERVED_RTX2000_ADA_GUARDED_BATCH_SECONDS
        + RUNPOD_BILLING_CYCLE_SECONDS
        + GUARDED_BILLING_RETRY_MARGIN_SECONDS
    )


def default_billing_attempts(retry_seconds: float = DEFAULT_BILLING_RETRY_SECONDS) -> int:
    return math.ceil(default_billing_max_wait_seconds() / retry_seconds)


def _positive_number(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _positive_int(value: str, name: str) -> int:
    number = int(value)
    if number <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return number


def _positive_float(value: str, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def billing_retry_config() -> tuple[int, float]:
    retry_seconds = DEFAULT_BILLING_RETRY_SECONDS
    if raw_retry_seconds := os.environ.get("RTF_RUNPOD_BILLING_RETRY_SECONDS"):
        retry_seconds = _positive_float(raw_retry_seconds, "RTF_RUNPOD_BILLING_RETRY_SECONDS")
    if raw_max_wait := os.environ.get("RTF_RUNPOD_BILLING_MAX_WAIT_SECONDS"):
        max_wait_seconds = _positive_float(raw_max_wait, "RTF_RUNPOD_BILLING_MAX_WAIT_SECONDS")
        attempts = math.ceil(max_wait_seconds / retry_seconds)
    elif raw_attempts := os.environ.get("RTF_RUNPOD_BILLING_ATTEMPTS"):
        attempts = _positive_int(raw_attempts, "RTF_RUNPOD_BILLING_ATTEMPTS")
    else:
        attempts = default_billing_attempts(retry_seconds)
    return attempts, retry_seconds


def resolve_runpod_token() -> str:
    for key in ("RUNPOD_TOKEN", "RUNPOD_API_KEY", "RUNPOD_API"):
        value = os.environ.get(key)
        if value:
            return value
    raise SystemExit("RUNPOD_TOKEN is required for RunPod billing metadata collection")


def _request_json(url: str, token: str) -> Any:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def _filter_pod_records(payload: Any, pod_id: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("RunPod billing response is not a list")
    return [
        item
        for item in payload
        if isinstance(item, dict) and item.get("podId") == pod_id
    ]


def fetch_billing_history(
    pod_id: str,
    token: str,
    *,
    attempts: int | None = None,
    retry_seconds: float = DEFAULT_BILLING_RETRY_SECONDS,
    request_json: Callable[[str, str], Any] = _request_json,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    if attempts is None:
        attempts, retry_seconds = billing_retry_config()
    query = urllib.parse.urlencode({"podId": pod_id, "grouping": "podId", "bucketSize": "hour"})
    url = f"{RUNPOD_BILLING_URL}?{query}"
    emit = log or (lambda message: print(message, file=sys.stderr, flush=True))
    cost_mode = os.environ.get("RTF_COST_MODE", "guarded")
    max_wait_seconds = attempts * retry_seconds
    emit(
        f"RunPod billing history lookup for Pod {pod_id}: "
        f"cost_mode={cost_mode}, attempts={attempts}, retry_seconds={retry_seconds}, "
        f"max_wait_seconds={max_wait_seconds:.0f}"
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            records = _filter_pod_records(request_json(url, token), pod_id)
            if records:
                if attempt > 1:
                    emit(
                        f"RunPod billing history available for Pod {pod_id} "
                        f"after attempt {attempt}/{attempts}"
                    )
                return records
            emit(
                f"RunPod billing history empty for Pod {pod_id}; "
                f"attempt {attempt}/{attempts}"
            )
        except Exception as error:  # noqa: BLE001 - retry provider eventual consistency
            last_error = error
            emit(
                f"RunPod billing history request failed for Pod {pod_id}; "
                f"attempt {attempt}/{attempts}: {error}"
            )
        if attempt < attempts:
            sleep(retry_seconds)
    if last_error is not None:
        raise RuntimeError(f"RunPod billing history unavailable: {last_error}") from last_error
    raise RuntimeError(f"RunPod billing history has no record for Pod {pod_id}")


def _gpu_type_ids_from_records(records: list[dict[str, Any]]) -> set[str]:
    return {item.get("gpuTypeId") for item in records if item.get("gpuTypeId")}


def fetch_gpu_type_id_from_billing(
    pod_id: str,
    token: str,
    *,
    request_json: Callable[[str, str], Any] = _request_json,
) -> str:
    # grouping=podId records omit gpuTypeId per RunPod API docs; query by gpuTypeId instead.
    query = urllib.parse.urlencode({"podId": pod_id, "grouping": "gpuTypeId", "bucketSize": "hour"})
    url = f"{RUNPOD_BILLING_URL}?{query}"
    payload = request_json(url, token)
    if not isinstance(payload, list):
        raise ValueError("RunPod billing gpuType lookup response is not a list")
    gpu_types = _gpu_type_ids_from_records(payload)
    if len(gpu_types) != 1:
        raise ValueError("RunPod billing history has no unique gpuTypeId")
    return next(iter(gpu_types))


def resolve_gpu_type_id(
    pod_id: str,
    records: list[dict[str, Any]],
    token: str,
    *,
    request_json: Callable[[str, str], Any] = _request_json,
) -> str:
    gpu_types = _gpu_type_ids_from_records(records)
    if len(gpu_types) == 1:
        return next(iter(gpu_types))
    if gpu_types:
        raise ValueError("RunPod billing history has no unique gpuTypeId")
    return fetch_gpu_type_id_from_billing(pod_id, token, request_json=request_json)


def probe_billing_api(
    token: str,
    *,
    request_json: Callable[[str, str], Any] = _request_json,
) -> None:
    """Verify RunPod billing API accepts the token before benchmark execution."""
    query = urllib.parse.urlencode({"grouping": "gpuTypeId", "bucketSize": "hour"})
    url = f"{RUNPOD_BILLING_URL}?{query}"
    payload = request_json(url, token)
    if not isinstance(payload, list):
        raise ValueError("RunPod billing probe response is not a list")


def build_billing_metadata(
    pod_id: str,
    records: list[dict[str, Any]],
    *,
    gpu_type_id: str,
) -> dict[str, Any]:
    amount = sum(_positive_number(item.get("amount"), "billing amount") for item in records)
    billed_ms = sum(int(item.get("timeBilledMs", 0)) for item in records)
    if billed_ms <= 0:
        raise ValueError("RunPod billing history has no positive timeBilledMs")
    billed_seconds = billed_ms // 1000
    if billed_seconds <= 0:
        raise ValueError("RunPod billing history duration is below one second")
    return {
        "provider": "runpod-pod",
        "job_id": pod_id,
        "url": f"https://console.runpod.io/pods/{pod_id}",
        "gpu_type_id": gpu_type_id,
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
    runpod_token = resolve_runpod_token()
    hf_token = os.environ.get("HF_TOKEN")
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

    attempts, retry_seconds = billing_retry_config()
    records = fetch_billing_history(
        pod_id,
        runpod_token,
        attempts=attempts,
        retry_seconds=retry_seconds,
    )
    gpu_type_id = resolve_gpu_type_id(pod_id, records, runpod_token)
    metadata = build_billing_metadata(pod_id, records, gpu_type_id=gpu_type_id)
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
