#!/usr/bin/env python3
"""Join the pinned RTF service policy with a RunPod GPU inventory response."""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-gpu")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    if not isinstance(inventory, list):
        raise SystemExit("RunPod inventory must be a JSON array")
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
    report = {
        "schema_version": 1,
        "service_id": config["service_id"],
        "observed_policy": {
            "minimum_cuda_version": minimum_cuda,
            "cuda_check": "RunPod pod create --min-cuda-version",
        },
        "entries": results,
        "selectable": [r["gpu"] for r in results if r["selectable"]],
    }
    if args.require_gpu:
        match = next((r for r in results if r["gpu"] == args.require_gpu), None)
        if match is None:
            raise SystemExit(f"GPU is not in .github/runpod-rtf-services.json: {args.require_gpu}")
        if not match["selectable"]:
            raise SystemExit(f"RunPod GPU is not currently selectable: {args.require_gpu}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
