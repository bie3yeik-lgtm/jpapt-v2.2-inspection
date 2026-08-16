#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from parakeet_onnx.config import resolve_config
from parakeet_onnx.evaluation import validate_run_context
from parakeet_onnx.hf.revisions import load_revision_bundle
from parakeet_onnx.run_context import build_run_context
from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate the canonical run-context snapshot for the Rust evaluator."
    )
    p.add_argument("--provider", required=True)
    p.add_argument("--evaluation", required=True)
    p.add_argument("--environment", required=True)
    p.add_argument("--model-config", required=True)
    p.add_argument("--candidate-dir", type=Path, required=True)
    p.add_argument("--runtime-variant")
    p.add_argument("--experiment-id")
    p.add_argument("--revisions", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--strict-provider",
        action="store_true",
        help="Disable CPU fallback for non-CPU provider proof runs.",
    )
    p.add_argument(
        "--optimization-level",
        choices=("configured", "disable", "basic", "extended", "all"),
        default="configured",
        help="Override ORT graph optimization for diagnostic A/B runs.",
    )
    return p


def _apply_runtime_overrides(
    context: dict[str, object],
    *,
    strict_provider: bool,
    optimization_level: str,
) -> None:
    config = context["config"]
    assert isinstance(config, dict)
    resolved = config["resolved"]
    assert isinstance(resolved, dict)
    provider = resolved["provider"]
    assert isinstance(provider, dict)

    session = provider.setdefault("session", {})
    assert isinstance(session, dict)
    validation = provider.setdefault("validation", {})
    assert isinstance(validation, dict)

    if optimization_level != "configured":
        session["graph_optimization_level"] = optimization_level
    if strict_provider:
        validation["strict_provider_mode"] = True
        validation["allow_cpu_fallback"] = False

    metadata = context.setdefault("metadata", {})
    assert isinstance(metadata, dict)
    metadata["runtime_overrides"] = {
        "strict_provider": strict_provider,
        "optimization_level": optimization_level,
    }


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

    metadata: dict[str, object] = {
        "candidate": candidate.provenance_dict(),
        "runtime_variant": candidate.variant,
        "runtime_profile": candidate.profile_id,
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
        candidate_path=candidate.primary_artifact.path,
        candidate_id=candidate.candidate_id,
        artifact_role=candidate.primary_artifact.role,
        metadata=metadata,
    ).to_dict()

    context["runtime"] = {
        "implementation": "rust",
        "backend": "onnxruntime",
        "backend_version": None,
        "provider_id": config.provider.id,
        "provider_ort_name": config.provider.ort_name,
        "provider_available": None,
    }
    _apply_runtime_overrides(
        context,
        strict_provider=args.strict_provider,
        optimization_level=args.optimization_level,
    )
    validate_run_context(context)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"run_context={args.output.resolve()}")
    print(f"run_id={context['run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
