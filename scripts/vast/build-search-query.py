#!/usr/bin/env python3
"""Build a Vast CLI search query from workflow inputs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

GPU_NAME_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")
NUM_GPUS_RE = re.compile(r"^(?:(>=|<=|>|<|=))?([0-9]+)$")
FILTER_SUFFIX_RE = re.compile(r"^(?:(>=|<=|>|<|=))?([0-9]+(?:\.[0-9]+)?)$")
NUM_GPUS_IN_RE = re.compile(r"^in\s*\[([0-9,\s]+)\]$", re.IGNORECASE)

BASE_FILTERS = (
    "verified=true",
    "rentable=true",
    "cuda_max_good>=13",
    "disk_space>=50",
)
GPU_ARCH_FILTER = "gpu_arch=nvidia"


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def _gpu_name_clause(raw: str) -> str:
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        _fail("gpu_name must not be empty when provided")
    for name in names:
        if not GPU_NAME_RE.fullmatch(name):
            _fail(f"gpu_name contains unsupported token: {name!r}")
    if len(names) == 1:
        return f"gpu_name={names[0]}"
    joined = ",".join(names)
    return f"gpu_name in [{joined}]"


def _num_gpus_clause(raw: str) -> str:
    value = raw.strip()
    in_match = NUM_GPUS_IN_RE.fullmatch(value)
    if in_match:
        items = [item.strip() for item in in_match.group(1).split(",") if item.strip()]
        if not items or not all(item.isdigit() for item in items):
            _fail(f"num_gpus list is invalid: {raw!r}")
        return f"num_gpus in [{','.join(items)}]"
    match = NUM_GPUS_RE.fullmatch(value)
    if not match:
        _fail(f"num_gpus must look like 1, >=2, or in [1,2,4]: {raw!r}")
    operator, number = match.groups()
    return f"num_gpus{operator or '='}{number}"


def _numeric_clause(field: str, raw: str) -> str:
    value = raw.strip()
    match = FILTER_SUFFIX_RE.fullmatch(value)
    if not match:
        _fail(f"{field} must look like 48, >=48, or <=96000: {raw!r}")
    operator, number = match.groups()
    return f"{field}{operator or '='}{number}"


def build_search_query(
    *,
    gpu_name: str = "",
    num_gpus: str = "",
    gpu_ram: str = "",
    duration: str = "",
) -> dict[str, Any]:
    optional_filters: list[str] = []
    user_inputs: dict[str, str] = {}

    if gpu_name.strip():
        user_inputs["gpu_name"] = gpu_name.strip()
        optional_filters.append(_gpu_name_clause(gpu_name))
    if num_gpus.strip():
        user_inputs["num_gpus"] = num_gpus.strip()
        optional_filters.append(_num_gpus_clause(num_gpus))
    if gpu_ram.strip():
        user_inputs["gpu_ram"] = gpu_ram.strip()
        optional_filters.append(_numeric_clause("gpu_ram", gpu_ram))
    if duration.strip():
        user_inputs["duration"] = duration.strip()
        optional_filters.append(_numeric_clause("duration", duration))

    filters = list(BASE_FILTERS)
    include_gpu_arch = len(optional_filters) < 3
    if include_gpu_arch:
        filters.append(GPU_ARCH_FILTER)
    filters.extend(optional_filters)

    return {
        "query": " ".join(filters),
        "base_filters": list(BASE_FILTERS),
        "include_gpu_arch": include_gpu_arch,
        "user_inputs": user_inputs,
        "filter_count": len(filters),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu-name", default="")
    parser.add_argument("--num-gpus", default="")
    parser.add_argument("--gpu-ram", default="")
    parser.add_argument("--duration", default="")
    parser.add_argument("--output-json", type=str, default="")
    args = parser.parse_args()

    payload = build_search_query(
        gpu_name=args.gpu_name,
        num_gpus=args.num_gpus,
        gpu_ram=args.gpu_ram,
        duration=args.duration,
    )
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as handle:
            handle.write(encoded)
    print(payload["query"])


if __name__ == "__main__":
    main()
