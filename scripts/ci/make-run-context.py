#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from parakeet_onnx.config import ConfigError, resolve_config
from parakeet_onnx.contracts import ContractError
from parakeet_onnx.evaluation import EvaluationSchemaError, validate_run_context
from parakeet_onnx.hf.revisions import RevisionError, load_revision_bundle
from parakeet_onnx.run_context import build_run_context
from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError


DEFAULT_REVISIONS = Path(".ci/hf/config/revisions")


def _metadata(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}
    path = Path(value)
    raw = path.read_text(encoding="utf-8") if path.is_file() else value
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--metadata-json must resolve to a JSON object")
    if "candidate" in parsed:
        raise ValueError("--metadata-json must not override generated candidate identity")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a strict canonical run-context.json."
    )
    parser.add_argument("--model", default="parakeet-tdt_ctc-0.6b-ja")
    parser.add_argument("--provider", required=True, choices=("cpu", "cuda", "directml", "coreml"))
    parser.add_argument("--evaluation", required=True, choices=("smoke", "parity", "coreml-parity", "full"))
    parser.add_argument("--environment", choices=("linux", "windows", "macos"))
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--runtime-variant")
    parser.add_argument("--revisions", type=Path, default=DEFAULT_REVISIONS)
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--metadata-json")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repository_root = (
        args.repository_root.expanduser().resolve()
        if args.repository_root is not None
        else None
    )
    try:
        config = resolve_config(
            model=args.model,
            provider=args.provider,
            evaluation=args.evaluation,
            environment=args.environment,
            repository_root=repository_root,
        )
        revisions = load_revision_bundle(args.revisions.expanduser().resolve())
        candidate = CandidateArtifacts.load(
            args.candidate_dir,
            variant=args.runtime_variant,
            repository_root=config.repository_root,
        )
        context = build_run_context(
            config=config,
            revisions=revisions,
            candidate=candidate,
            metadata=_metadata(args.metadata_json),
            run_id=args.run_id,
        )
        validate_run_context(context, repository_root=config.repository_root)
        context.write_json(args.output.expanduser())
    except (
        ConfigError,
        ContractError,
        RevisionError,
        CandidateMetadataError,
        EvaluationSchemaError,
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ) as exc:
        print(f"ERROR: failed to create run context: {exc}", file=sys.stderr)
        return 1

    print("Run context created.")
    print(f"run_id: {context.run_id}")
    print(f"output: {args.output.expanduser().resolve()}")
    print(f"artifact_sha256: {context.artifact.sha256}")
    print(f"revision_bundle_sha256: {revisions.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
