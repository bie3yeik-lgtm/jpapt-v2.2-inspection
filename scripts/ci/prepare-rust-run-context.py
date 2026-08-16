#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from parakeet_onnx.config import resolve_config
from parakeet_onnx.contracts import ContractError
from parakeet_onnx.evaluation import validate_run_context
from parakeet_onnx.hf.revisions import load_revision_bundle
from parakeet_onnx.run_context import build_run_context
from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate the strict canonical run-context snapshot for the Rust evaluator."
    )
    p.add_argument("--provider", required=True, choices=("cpu", "cuda", "directml", "coreml"))
    p.add_argument("--evaluation", required=True, choices=("smoke", "parity", "coreml-parity", "full"))
    p.add_argument("--environment", required=True, choices=("linux", "windows", "macos"))
    p.add_argument("--model-config", required=True)
    p.add_argument("--candidate-dir", type=Path, required=True)
    p.add_argument("--runtime-variant")
    p.add_argument("--experiment-id")
    p.add_argument("--revisions", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--strict-provider", action="store_true")
    p.add_argument(
        "--optimization-level",
        choices=("configured", "disable", "basic", "extended", "all"),
        default="configured",
    )
    return p


def _mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if value is None:
        value = {}
        parent[key] = value
    if not isinstance(value, dict):
        raise ContractError(f"resolved config {key!r} must be an object")
    return value


def _apply_runtime_overrides(
    resolved: dict[str, Any],
    *,
    strict_provider: bool,
    optimization_level: str,
) -> None:
    provider = _mapping(resolved, "provider")
    session = _mapping(provider, "session")
    validation = _mapping(provider, "validation")
    if optimization_level != "configured":
        session["graph_optimization_level"] = optimization_level
    if strict_provider:
        validation["strict_provider_mode"] = True
        validation["allow_cpu_fallback"] = False


def main() -> int:
    args = parser().parse_args()
    config = resolve_config(
        model=args.model_config,
        provider=args.provider,
        evaluation=args.evaluation,
        environment=args.environment,
    )
    revisions = load_revision_bundle(args.revisions)
    candidate = CandidateArtifacts.load(
        args.candidate_dir,
        variant=args.runtime_variant,
        repository_root=config.repository_root,
    )
    validate_candidate_runtime_contract(candidate)
    _apply_runtime_overrides(
        config.merged,
        strict_provider=args.strict_provider,
        optimization_level=args.optimization_level,
    )

    metadata: dict[str, object] = {
        "runtime_overrides": {
            "strict_provider": args.strict_provider,
            "optimization_level": args.optimization_level,
        }
    }
    if args.experiment_id:
        metadata["experiment_id"] = args.experiment_id
    for key, env_name in (
        ("hf_target_id", "HF_TARGET_ID"),
        ("hf_bucket", "HF_BUCKET"),
        ("hf_model_repo", "HF_MODEL_REPO"),
    ):
        value = os.environ.get(env_name)
        if value:
            metadata[key] = value

    context = build_run_context(
        config=config,
        revisions=revisions,
        candidate=candidate,
        runtime_implementation="rust",
        runtime_backend_version="resolved-by-rust-runtime",
        provider_available=False,
        metadata=metadata,
    )
    validate_run_context(context, repository_root=config.repository_root)
    context.write_json(args.output)
    print(f"run_context={args.output.resolve()}")
    print(f"run_id={context.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
