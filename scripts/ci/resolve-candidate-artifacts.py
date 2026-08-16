#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve one selected candidate runtime variant into CI outputs."
    )
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--runtime-variant")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--github-output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        candidate = CandidateArtifacts.load(
            args.candidate_dir,
            variant=args.runtime_variant,
            repository_root=args.repository_root,
        )
        validate_candidate_runtime_contract(candidate)
    except (CandidateMetadataError, KeyError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    values: dict[str, str] = {
        "candidate_id": candidate.candidate_id,
        "profile_set": candidate.profile_set_id or "legacy",
        "runtime_variant": candidate.variant or candidate.decoder,
        "runtime_profile": candidate.profile_id or "legacy",
        "decoder": candidate.decoder,
        "artifact_contract": candidate.artifact_contract,
        "bundle_sha256": candidate.bundle_sha256,
        "primary_artifact": str(candidate.primary_artifact.path),
    }
    for role, artifact in sorted(candidate.artifacts.items()):
        safe_role = role.replace("-", "_")
        values[f"artifact_{safe_role}"] = str(artifact.path)
    if candidate.tokenizer is not None:
        values["tokenizer_kind"] = candidate.tokenizer.kind
        values["tokenizer_path"] = str(candidate.tokenizer.path)

    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    for key, value in values.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
