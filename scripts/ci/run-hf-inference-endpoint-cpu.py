#!/usr/bin/env python3
"""Measure a pre-provisioned Hugging Face CPU Inference Endpoint.

The endpoint must expose an audio-to-text HTTP contract. This adapter keeps
endpoint lifecycle and model hosting outside the benchmark workflow, while
recording client-observed service RTF against the pinned fixture.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import jiwer


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint-url", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--model-id", required=True)
    p.add_argument("--model-revision", required=True)
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--dataset-revision", required=True)
    p.add_argument("--fixture-repo-id", required=True)
    p.add_argument("--fixture-revision", required=True)
    p.add_argument("--manifest-sha256", required=True)
    p.add_argument("--image-digest", required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--cpu-target", required=True)
    p.add_argument("--batch-size", type=int, choices=(1, 8, 32), required=True)
    p.add_argument("--profile", choices=("smoke", "pref", "probe"), default="smoke")
    p.add_argument("--price-per-hour", type=float, default=None)
    return p


def load_samples(path: Path) -> list[dict[str, object]]:
    samples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not samples:
        raise ValueError("manifest is empty")
    for sample in samples:
        audio_path = sample.get("audio_path")
        if not isinstance(audio_path, str) or not Path(audio_path).is_file():
            raise ValueError(f"audio_path is not a materialized file: {audio_path}")
    return samples


def response_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("text", "generated_text", "transcription"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        if isinstance(payload.get("data"), dict):
            return response_text(payload["data"])
    if isinstance(payload, list) and payload:
        return response_text(payload[0])
    raise ValueError("endpoint response did not contain text/generated_text/transcription")


def call_endpoint(url: str, token: str, audio_path: str) -> str:
    request = urllib.request.Request(
        url,
        data=Path(audio_path).read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "audio/wav"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        body = response.read()
    try:
        return response_text(json.loads(body))
    except json.JSONDecodeError:
        return response_text(body.decode("utf-8"))


def main() -> int:
    args = parser().parse_args()
    samples = load_samples(args.manifest)
    durations = [float(sample["audio_duration_sec"]) for sample in samples]
    references = [str(sample.get("text", "")) for sample in samples]
    timings: list[float] = []
    cer_values: list[float] = []
    try:
        for _ in range(args.batch_size):
            started = time.perf_counter()
            hypotheses = [call_endpoint(args.endpoint_url, args.token, str(sample["audio_path"])) for sample in samples]
            elapsed = time.perf_counter() - started
            timings.append(elapsed)
            reference = " ".join(references).strip()
            if reference:
                cer_values.append(jiwer.cer(reference, " ".join(hypotheses).strip()))
        audio_duration = sum(durations)
        processing = max(statistics.median(timings), 1e-9)
        rtf = processing / audio_duration
        result = {
            "schema_version": 1,
            "run_id": args.run_id,
            "status": "completed",
            "model_id": args.model_id,
            "model_revision": args.model_revision,
            "dataset_id": args.dataset_id,
            "dataset_revision": args.dataset_revision,
            "manifest_sha256": args.manifest_sha256,
            "image_digest": args.image_digest,
            "inspection_profile": args.profile,
            "fixture_repo_id": args.fixture_repo_id,
            "fixture_revision": args.fixture_revision,
            "decoder": "tdt",
            "precision": "float32",
            "audio_duration_sec": audio_duration,
            "processing_duration_sec": processing,
            "rtf": rtf,
            "rtfx": audio_duration / processing,
            "rtf_scope": "service",
            "provider": "cpu",
            "environment": "linux",
            "service_id": "hf-inference-endpoint",
            "gpu": args.cpu_target,
            "dtype": "float32",
            "batch_size": args.batch_size,
            "repeat": args.batch_size,
            "cer": statistics.median(cer_values) if cer_values else None,
            "peak_vram_bytes": None,
            "gpu_utilization_pct": None,
            "memory_bandwidth_utilization_pct": None,
            "queue_latency_sec": None,
            "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "gpu_price_per_hour": args.price_per_hour,
            "cost_per_audio_hour": args.price_per_hour * rtf if args.price_per_hour is not None else None,
        }
    except Exception as exc:
        result = {
            "schema_version": 1,
            "run_id": args.run_id,
            "status": "blocked",
            "error_code": "HF_ENDPOINT_CPU_REQUEST_FAILED",
            "error_message": str(exc),
            "model_id": args.model_id,
            "model_revision": args.model_revision,
            "dataset_id": args.dataset_id,
            "dataset_revision": args.dataset_revision,
            "manifest_sha256": args.manifest_sha256,
            "image_digest": args.image_digest,
            "inspection_profile": args.profile,
            "fixture_repo_id": args.fixture_repo_id,
            "fixture_revision": args.fixture_revision,
            "decoder": "tdt",
            "precision": "float32",
            "provider": "cpu",
            "environment": "linux",
            "service_id": "hf-inference-endpoint",
            "gpu": args.cpu_target,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
