#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("smoke", "pref", "probe"), required=True)
    parser.add_argument("--service-result", type=Path, required=True)
    args = parser.parse_args()
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    service_result = json.loads(args.service_result.read_text(encoding="utf-8"))
    if metrics.get("status") != "completed" or service_result.get("status") != "completed":
        raise SystemExit("only completed results can become benchmark records")
    if service_result.get("metrics_sha256") != hashlib.sha256(args.metrics.read_bytes()).hexdigest():
        raise SystemExit("metrics SHA-256 mismatch")
    for field in ("run_id", "service_id", "gpu"):
        if service_result.get(field) not in (None, metrics.get(field)):
            raise SystemExit(f"service result {field} does not match metrics")
    record = {
        "schema_version": 1,
        "run_id": metrics["run_id"],
        "phase": {"smoke": "phase1", "pref": "pref", "probe": "probe"}[args.profile],
        "service_id": metrics["service_id"],
        "gpu": metrics["gpu"],
        "model_id": metrics["model_id"],
        "decoder": metrics["decoder"],
        "dataset_manifest_id": "benchmark-v1",
        "dataset_manifest_sha256": metrics["manifest_sha256"],
        "dataset_revision": metrics["dataset_revision"],
        "fixture_repo_id": metrics["fixture_repo_id"],
        "fixture_revision": metrics["fixture_revision"],
        "image_digest": metrics["image_digest"],
        "batch_size": metrics["batch_size"],
        "repeat": metrics["repeat"],
        "precision": metrics["dtype"],
        "status": "completed",
        "provider_execution_proof": metrics["provider"] in {"cpu", "cuda"} and metrics["environment"] == "linux",
        "audio_duration_sec": metrics["audio_duration_sec"],
        "processing_duration_sec": metrics["processing_duration_sec"],
        "rtf": metrics["rtf"],
        "rtfx": metrics["rtfx"],
        "rtf_scope": metrics["rtf_scope"],
        "cer": metrics["cer"],
        "wer": None,
        "peak_vram_mb": (metrics["peak_vram_bytes"] / 1048576) if metrics["peak_vram_bytes"] is not None else None,
        "gpu_utilization_percent": metrics["gpu_utilization_pct"],
        "gpu_price_per_hour": metrics["gpu_price_per_hour"],
        "cost_per_audio_hour": metrics["cost_per_audio_hour"],
        "completed_at": metrics.get("completed_at"),
        "metrics_uri": service_result["metrics_uri"],
        "metrics_sha256": service_result["metrics_sha256"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
