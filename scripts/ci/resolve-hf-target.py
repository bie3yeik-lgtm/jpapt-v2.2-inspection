#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys
from typing import Any

from parakeet_onnx.config.resolver import ConfigResolver
from parakeet_onnx.hf.targets import HfTargetError, load_hf_target_by_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve one Hugging Face ASR development target."
    )
    parser.add_argument(
        "--target",
        help=(
            "Optional explicit target id. Use this to disambiguate a Bucket "
            "shared by multiple targets."
        ),
    )
    parser.add_argument(
        "--bucket",
        help=(
            "Current operational HF_BUCKET. Bucket routing may change over time "
            "for capacity or workflow purposes."
        ),
    )
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--targets-json",
        help=(
            "Optional JSON object keyed by target id. Each entry supplies the "
            "current HF_BUCKET and HF_MODEL_REPO routing."
        ),
    )
    parser.add_argument("--github-env", type=Path)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--shell", action="store_true")
    return parser


def _load_target_mapping(raw_json: str | None) -> dict[str, dict[str, str]]:
    if raw_json is None or not raw_json.strip():
        return {}

    try:
        raw: Any = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise HfTargetError(
            f"HF target mapping is not valid JSON: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise HfTargetError("HF target mapping root must be a JSON object.")

    result: dict[str, dict[str, str]] = {}
    for target_id, entry in raw.items():
        if not isinstance(target_id, str) or not target_id:
            raise HfTargetError("HF target mapping keys must be non-empty strings.")
        if not isinstance(entry, dict):
            raise HfTargetError(
                f"HF target mapping entry {target_id!r} must be a JSON object."
            )

        normalized: dict[str, str] = {}
        for key in ("HF_BUCKET", "HF_MODEL_REPO"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                raise HfTargetError(
                    f"HF target mapping entry {target_id!r}.{key} "
                    "must be a non-empty string."
                )
            normalized[key] = value.strip()

        result[target_id] = normalized

    return result


def _target_id_from_bucket(
    *,
    bucket: str,
    mapping: dict[str, dict[str, str]],
) -> str:
    if not mapping:
        raise HfTargetError(
            "--bucket requires --targets-json because Bucket-to-target "
            "resolution is defined by the current vars.HF_TARGETS_JSON routing."
        )
    matches = [
        target_id
        for target_id, entry in mapping.items()
        if entry["HF_BUCKET"] == bucket
    ]
    if not matches:
        available = sorted({entry["HF_BUCKET"] for entry in mapping.values()})
        raise HfTargetError(
            f"HF_BUCKET {bucket!r} is not present in the current HF target mapping. "
            f"Available buckets: {available!r}"
        )
    if len(matches) > 1:
        raise HfTargetError(
            f"HF_BUCKET {bucket!r} currently maps to multiple targets: {matches!r}. "
            "Bucket sharing is allowed; provide --target to disambiguate."
        )
    return matches[0]


def main() -> int:
    args = build_parser().parse_args()
    root = args.repository_root.expanduser().resolve()

    if args.target is None and args.bucket is None:
        print("ERROR: at least one of --target or --bucket is required", file=sys.stderr)
        return 2

    try:
        mapping = _load_target_mapping(args.targets_json)

        if args.target is not None:
            target_id = args.target
        else:
            assert args.bucket is not None
            target_id = _target_id_from_bucket(bucket=args.bucket, mapping=mapping)

        target = load_hf_target_by_id(target_id, repository_root=root)
        model = ConfigResolver(root).load_model(target.model_id)

        if model.upstream_repo_id != target.upstream_repo_id:
            raise HfTargetError(
                "HF target upstream repo does not match model config: "
                f"target={target.upstream_repo_id!r}, "
                f"model={model.upstream_repo_id!r}"
            )
        framework = model.get("model.framework")
        if framework != target.canonical_framework:
            raise HfTargetError(
                "HF target canonical framework does not match model config: "
                f"target={target.canonical_framework!r}, "
                f"model={framework!r}"
            )

        storage_override = mapping.get(target.id, {})
        if mapping and not storage_override:
            raise HfTargetError(
                f"HF target mapping does not contain target {target.id!r}."
            )

        resolved_bucket = storage_override.get("HF_BUCKET", target.bucket)
        if args.bucket is not None and resolved_bucket != args.bucket:
            raise HfTargetError(
                f"Target {target.id!r} currently routes to HF_BUCKET "
                f"{resolved_bucket!r}, not requested bucket {args.bucket!r}."
            )
    except (HfTargetError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    bucket = storage_override.get("HF_BUCKET", target.bucket)
    model_repo = storage_override.get("HF_MODEL_REPO", target.model_repo)

    values = {
        "HF_BUCKET": bucket,
        "HF_MODEL_REPO": model_repo,
        "EXPECTED_DEVELOPMENT_REPO_ID": model_repo,
        "EXPECTED_UPSTREAM_REPO_ID": target.upstream_repo_id,
        "EXPECTED_TOKENIZER_REPO_ID": target.upstream_repo_id,
        "EXPECTED_FRAMEWORK": target.canonical_framework,
        "EXPECTED_DECODER": target.default_decoder,
        "HF_TARGET_ID": target.id,
    }

    if args.github_env is not None:
        with args.github_env.open("a", encoding="utf-8") as file:
            for key, value in values.items():
                file.write(f"{key}={value}\n")

    if args.github_output is not None:
        outputs = {
            "target_id": target.id,
            "hf_bucket": bucket,
            "hf_model_repo": model_repo,
            "decoder": target.default_decoder,
            "framework": target.canonical_framework,
        }
        with args.github_output.open("a", encoding="utf-8") as file:
            for key, value in outputs.items():
                file.write(f"{key}={value}\n")

    if args.shell:
        for key, value in values.items():
            print(f"export {key}={shlex.quote(value)}")
    else:
        for key, value in values.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
