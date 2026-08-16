#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve a minimal candidate into one generated execution contract."
    )
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--runtime-variant")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--contract-out", type=Path)
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
        contract = candidate.generated_contract().to_dict()
    except (CandidateMetadataError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    values: dict[str, str] = {
        "candidate_id": candidate.candidate_id,
        "profile_set": candidate.profile_set_id,
        "runtime_variant": candidate.variant,
        "runtime_profile": candidate.profile_id,
        "decoder": candidate.decoder,
        "artifact_contract": candidate.artifact_contract,
        "bundle_sha256": candidate.bundle_sha256,
        "primary_artifact": str(candidate.primary_artifact.path),
        "catalog_id": candidate.catalog_id,
        "catalog_sha256": candidate.catalog_sha256,
    }
    for role, artifact in sorted(candidate.artifacts.items()):
        safe_role = role.replace("-", "_")
        values[f"artifact_{safe_role}"] = str(artifact.path)
        values[f"artifact_{safe_role}_sha256"] = artifact.sha256
        values[f"artifact_{safe_role}_size_bytes"] = str(artifact.size_bytes)
    if candidate.tokenizer is not None:
        values["tokenizer_kind"] = candidate.tokenizer.kind
        values["tokenizer_path"] = str(candidate.tokenizer.path)

    if args.contract_out is not None:
        args.contract_out.parent.mkdir(parents=True, exist_ok=True)
        args.contract_out.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        values["candidate_contract"] = str(args.contract_out.resolve())

    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    for key, value in values.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
