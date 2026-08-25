#!/usr/bin/env python3
"""Join the pinned RTF service policy with a RunPod GPU inventory response."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def build_report(config: dict[str, Any], inventory: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(item.get("gpuId", item.get("gpu_id", ""))): item for item in inventory}
    minimum_cuda = config["minimum_cuda_version"]
    allowed_clouds = set(config["cloud_types"])
    results = []
    for entry in config["entries"]:
        item = by_id.get(entry["gpu_id"], {})
        available = item.get("available") is True
        secure = item.get("secureCloud", item.get("secure_cloud")) is True
        community = item.get("communityCloud", item.get("community_cloud")) is True
        results.append({
            "service_id": config["service_id"],
            "provider": config["provider"],
            "environment": config["environment"],
            "gpu": entry["gpu"],
            "gpu_id": entry["gpu_id"],
            "available": available,
            "secure_cloud": secure,
            "community_cloud": community,
            "cuda_requirement": minimum_cuda,
            "cuda_requirement_status": "enforced_at_pod_create",
            "selectable": available and (
                (secure and "SECURE" in allowed_clouds)
                or (community and "COMMUNITY" in allowed_clouds)
            ),
            "stock_status": item.get("stockStatus", item.get("stock_status")),
        })
    return {
        "schema_version": 1,
        "service_id": config["service_id"],
        "observed_policy": {
            "minimum_cuda_version": minimum_cuda,
            "cuda_check": "RunPod pod create --min-cuda-version",
        },
        "entries": results,
        "selectable": [r["gpu"] for r in results if r["selectable"]],
    }


def _format_require_gpu_failure(require_gpu: str, match: dict[str, Any] | None) -> str:
    if match is None:
        return f"GPU is not in .github/runpod-rtf-services.json: {require_gpu}"
    return (
        f"RunPod GPU is not currently selectable: {require_gpu} "
        f"(available={match['available']}, secure={match['secure_cloud']}, "
        f"community={match['community_cloud']}, stock={match.get('stock_status')})"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-gpu")
    parser.add_argument("--require-gpu-attempts", type=int, default=0)
    parser.add_argument("--require-gpu-retry-seconds", type=int, default=30)
    parser.add_argument("--refresh-command")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    attempts = args.require_gpu_attempts or (3 if args.require_gpu else 1)
    if attempts < 1:
        raise SystemExit("--require-gpu-attempts must be at least 1")

    report: dict[str, Any] | None = None
    required_match: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        if not isinstance(inventory, list):
            raise SystemExit("RunPod inventory must be a JSON array")
        report = build_report(config, inventory)
        if not args.require_gpu:
            break

        required_match = next((entry for entry in report["entries"] if entry["gpu"] == args.require_gpu), None)
        if required_match is None:
            break
        if required_match["selectable"]:
            break
        if attempt >= attempts:
            break
        print(
            f"RunPod GPU inventory attempt {attempt}/{attempts} for {args.require_gpu} "
            f"was not selectable; retrying in {args.require_gpu_retry_seconds}s",
            file=sys.stderr,
        )
        if args.refresh_command:
            subprocess.run(args.refresh_command, shell=True, check=True)
        time.sleep(args.require_gpu_retry_seconds)

    assert report is not None
    if args.require_gpu:
        if required_match is None:
            raise SystemExit(_format_require_gpu_failure(args.require_gpu, None))
        if not required_match["selectable"]:
            raise SystemExit(_format_require_gpu_failure(args.require_gpu, required_match))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
