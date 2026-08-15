#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import sys

from parakeet_onnx.config.resolver import ConfigResolver
from parakeet_onnx.hf.targets import (
    HfTargetError,
    load_hf_target_by_id,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve one static Hugging Face ASR development target."
    )
    parser.add_argument("--target", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--github-env",
        type=Path,
        help="Append resolved values to a GitHub Actions GITHUB_ENV file.",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Print shell export commands.",
    )
    return parser


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

        model_framework = model.get("model.framework")
        if model_framework != target.canonical_framework:
            raise HfTargetError(
                "HF target canonical framework does not match model config: "
                f"target={target.canonical_framework!r}, "
                f"model={model_framework!r}"
            )

    except (HfTargetError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # reference.json identifies the development/release model repository whose
    # artifacts are being validated. The canonical upstream source remains a
    # separate, immutable identity in the static model/target configuration.
    values = {
        "HF_BUCKET": target.bucket,
        "HF_MODEL_REPO": target.model_repo,
        "EXPECTED_MODEL_ID": target.model_repo,
        "EXPECTED_UPSTREAM_MODEL_ID": target.upstream_repo_id,
        "EXPECTED_FRAMEWORK": target.canonical_framework,
        "EXPECTED_DECODER": target.default_decoder,
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
