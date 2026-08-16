#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib

from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that an evaluator supports the resolved decoder, provider, "
            "candidate artifact contract, runtime contract, and required features."
        )
    )
    parser.add_argument("--evaluator", required=True)
    parser.add_argument("--decoder", required=True)
    parser.add_argument("--provider")
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = (
        args.repository_root.expanduser().resolve()
        / "config"
        / "evaluators"
        / f"{args.evaluator}.toml"
    )
    if not path.is_file():
        return _error(f"evaluator capability file not found: {path}")

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        evaluator = raw["evaluator"]
        capabilities = raw["capabilities"]
        evaluator_id = evaluator["id"]
        supported_decoders = _string_list(capabilities, "supported_decoders")
        supported_providers = _string_list(
            capabilities, "supported_providers", required=False
        )
        supported_contracts = _string_list(
            capabilities, "supported_artifact_contracts", required=False
        )
        features_raw = raw.get("features", {})
        if not isinstance(features_raw, dict) or not all(
            isinstance(key, str) and isinstance(value, bool)
            for key, value in features_raw.items()
        ):
            return _error("features must be a TOML table of booleans")
    except (KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        return _error(f"invalid evaluator capability file {path}: {exc}")

    if evaluator_id != args.evaluator:
        return _error(
            f"evaluator id mismatch: requested={args.evaluator!r}, configured={evaluator_id!r}"
        )
    if args.decoder not in supported_decoders:
        return _error(
            "evaluator capability mismatch: "
            f"evaluator={args.evaluator!r}, decoder={args.decoder!r}, "
            f"supported={supported_decoders!r}"
        )
    if (
        args.provider is not None
        and supported_providers
        and args.provider not in supported_providers
    ):
        return _error(
            "evaluator provider mismatch: "
            f"evaluator={args.evaluator!r}, provider={args.provider!r}, "
            f"supported={supported_providers!r}"
        )

    candidate: CandidateArtifacts | None = None
    if args.candidate_dir is not None:
        try:
            candidate = CandidateArtifacts.load(args.candidate_dir)
            validate_candidate_runtime_contract(candidate)
        except (CandidateMetadataError, KeyError, TypeError, ValueError) as exc:
            return _error(f"candidate runtime contract is invalid: {exc}")
        if candidate.decoder != args.decoder:
            return _error(
                "candidate decoder mismatch: "
                f"expected={args.decoder!r}, candidate={candidate.decoder!r}"
            )
        if supported_contracts and candidate.artifact_contract not in supported_contracts:
            return _error(
                "candidate artifact contract is unsupported: "
                f"contract={candidate.artifact_contract!r}, "
                f"supported={supported_contracts!r}"
            )
        for feature, required in candidate.features.items():
            if required and not bool(features_raw.get(feature, False)):
                return _error(
                    "candidate requires unsupported evaluator feature: "
                    f"feature={feature!r}, evaluator={args.evaluator!r}"
                )

    suffix = ""
    if candidate is not None:
        suffix = (
            f", artifact_contract={candidate.artifact_contract}, "
            f"features={dict(candidate.features)!r}"
        )
    print(
        "Evaluator capability OK: "
        f"evaluator={args.evaluator}, decoder={args.decoder}, "
        f"provider={args.provider or 'not-checked'}{suffix}"
    )
    return 0


def _string_list(
    source: dict[str, object],
    key: str,
    *,
    required: bool = True,
) -> list[str]:
    value = source.get(key)
    if value is None and not required:
        return []
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"capabilities.{key} must be a non-empty string list")
    return list(value)


def _error(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
