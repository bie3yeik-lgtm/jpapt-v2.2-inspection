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
    parser.add_argument("--target", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--targets-json",
        help=(
            "Optional JSON object keyed by target id. Each entry may override "
            "HF_BUCKET and HF_MODEL_REPO from config/hf-targets/*.toml."
        ),
    )
    parser.add_argument("--github-env", type=Path)
    parser.add_argument("--shell", action="store_true")
    return parser


def _load_storage_override(
    *,
    target_id: str,
    raw_json: str | None,
) -> dict[str, str]:
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

    entry = raw.get(target_id)
    if entry is None:
        raise HfTargetError(
            f"HF target mapping does not contain target {target_id!r}."
        )
    if not isinstance(entry, dict):
        raise HfTargetError(
            f"HF target mapping entry {target_id!r} must be a JSON object."
        )

    result: dict[str, str] = {}
    for key in ("HF_BUCKET", "HF_MODEL_REPO"):
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            raise HfTargetError(
                f"HF target mapping entry {target_id!r}.{key} "
                "must be a non-empty string."
            )
        result[key] = value.strip()

    return result


def main() -> int:
    args = build_parser().parse_args()
    root = args.repository_root.expanduser().resolve()

    try:
        target = load_hf_target_by_id(args.target, repository_root=root)
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

        storage_override = _load_storage_override(
            target_id=target.id,
            raw_json=args.targets_json,
        )
    except (HfTargetError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    bucket = storage_override.get("HF_BUCKET", target.bucket)
    model_repo = storage_override.get("HF_MODEL_REPO", target.model_repo)

    values = {
        "HF_BUCKET": bucket,
        "HF_MODEL_REPO": model_repo,
        "EXPECTED_MODEL_ID": model_repo,
        "EXPECTED_UPSTREAM_MODEL_ID": target.upstream_repo_id,
        "EXPECTED_FRAMEWORK": target.canonical_framework,
        "EXPECTED_DECODER": target.default_decoder,
        "ALLOW_LEGACY_REVISION_METADATA": (
            "true" if target.allow_legacy_revision_metadata else "false"
        ),
        "HF_TARGET_ID": target.id,
    }

    if args.github_env is not None:
        with args.github_env.open("a", encoding="utf-8") as file:
            for key, value in values.items():
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
