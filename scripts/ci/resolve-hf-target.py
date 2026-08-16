#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys
from typing import Any

from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.config.resolver import ConfigResolver
from parakeet_onnx.hf.targets import HfTargetError, load_hf_target_by_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve one Hugging Face ASR development target."
    )
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--target")
    selector.add_argument(
        "--bucket",
        help=(
            "Resolve the target whose HF_BUCKET matches in the current "
            "--targets-json routing snapshot. Bucket assignments may change "
            "between snapshots."
        ),
    )
    parser.add_argument(
        "--runtime-variant",
        help=(
            "Optional runtime variant key from the target profile set, e.g. ctc or "
            "tdt. Omit to use the central profile-set default."
        ),
    )
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--targets-json",
        help=(
            "Optional JSON object keyed by target id. Each entry supplies the "
            "current HF_BUCKET and HF_MODEL_REPO routing. HF_BUCKET values "
            "must be unique within this snapshot, but may change over time."
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
        raise HfTargetError(f"HF target mapping is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise HfTargetError("HF target mapping root must be a JSON object.")

    result: dict[str, dict[str, str]] = {}
    seen_buckets: dict[str, str] = {}
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
                    f"HF target mapping entry {target_id!r}.{key} must be a non-empty string."
                )
            normalized[key] = value.strip()
        bucket = normalized["HF_BUCKET"]
        previous = seen_buckets.get(bucket)
        if previous is not None:
            raise HfTargetError(
                f"HF_BUCKET {bucket!r} is assigned to both {previous!r} and "
                f"{target_id!r} in the current routing snapshot."
            )
        seen_buckets[bucket] = target_id
        result[target_id] = normalized
    return result


def _target_id_from_bucket(
    *, bucket: str, mapping: dict[str, dict[str, str]]
) -> str:
    if not mapping:
        raise HfTargetError(
            "--bucket requires --targets-json because Bucket-to-target resolution "
            "is defined by the current vars.HF_TARGETS_JSON routing."
        )
    matches = [
        target_id
        for target_id, entry in mapping.items()
        if entry["HF_BUCKET"] == bucket
    ]
    if not matches:
        available = sorted(entry["HF_BUCKET"] for entry in mapping.values())
        raise HfTargetError(
            f"HF_BUCKET {bucket!r} is not present in the current HF target mapping. "
            f"Available buckets: {available!r}"
        )
    return matches[0]


def main() -> int:
    args = build_parser().parse_args()
    root = args.repository_root.expanduser().resolve()

    try:
        mapping = _load_target_mapping(args.targets_json)
        target_id = (
            args.target
            if args.target is not None
            else _target_id_from_bucket(bucket=args.bucket, mapping=mapping)
        )
        target = load_hf_target_by_id(target_id, repository_root=root)
        model = ConfigResolver(root).load_model(target.model_id)
        catalog = load_repository_catalog(root)
        profile_set = catalog.profile_set(target.profile_set_id)
        runtime_variant = args.runtime_variant or profile_set.default_variant
        runtime_profile = profile_set.profile_id_for(runtime_variant)
        decoder_profile = catalog.decoder_profile(runtime_profile)

        if model.upstream_repo_id != target.upstream_repo_id:
            raise HfTargetError(
                "HF target upstream repo does not match model config: "
                f"target={target.upstream_repo_id!r}, model={model.upstream_repo_id!r}"
            )
        framework = model.get("model.framework")
        if framework != target.canonical_framework:
            raise HfTargetError(
                "HF target canonical framework does not match model config: "
                f"target={target.canonical_framework!r}, model={framework!r}"
            )
        storage_override = mapping.get(target.id, {})
        if mapping and not storage_override:
            raise HfTargetError(
                f"HF target mapping does not contain target {target.id!r}."
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
        "HF_PROFILE_SET": target.profile_set_id,
        "ASR_RUNTIME_VARIANT": runtime_variant,
        "EXPECTED_RUNTIME_PROFILE": runtime_profile,
        "EXPECTED_DECODER": decoder_profile.decoder,
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
            "profile_set": target.profile_set_id,
            "runtime_variant": runtime_variant,
            "runtime_profile": runtime_profile,
            "decoder": decoder_profile.decoder,
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
