#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from parakeet_onnx.config import resolve_config
from parakeet_onnx.evaluation import validate_run_context
from parakeet_onnx.hf.revisions import load_revision_bundle
from parakeet_onnx.run_context import build_run_context
from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate the strict canonical run-context snapshot for the Rust evaluator."
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


def _normalize_rust_only_optionals(context: dict[str, Any]) -> None:
    """Normalize semantic optionals without inventing execution evidence."""
    host = context["host"]
    if not isinstance(host, dict):
        raise RuntimeError("run-context host must be an object")
    host["github_runner_os"] = host.get("github_runner_os") or "local"
    host["github_runner_arch"] = host.get("github_runner_arch") or "local"
    host["github_run_id"] = host.get("github_run_id") or "local"
    host["github_run_attempt"] = host.get("github_run_attempt") or "local"

    revisions = context["revisions"]
    if not isinstance(revisions, dict):
        raise RuntimeError("run-context revisions must be an object")
    if revisions.get("config_version") is None:
        revisions["config_version"] = "unversioned"
    datasets = revisions.get("datasets")
    if isinstance(datasets, dict):
        entries = datasets.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    raise RuntimeError("run-context dataset revision entry must be an object")
                entry["subset"] = entry.get("subset") or "default"
                entry["split"] = entry.get("split") or "default"
                entry["manifest"] = entry.get("manifest") or "unmaterialized"
                if entry.get("sha256") is None:
                    raise RuntimeError(
                        "Rust run-context requires datasets.entries[].sha256; identity is unknown"
                    )


def _require_concrete_git_identity(context: dict[str, Any]) -> None:
    git = context["git"]
    if not isinstance(git, dict):
        raise RuntimeError("run-context git must be an object")
    for key in ("repository", "commit", "ref", "dirty"):
        if git.get(key) is None:
            raise RuntimeError(
                f"Rust run-context requires concrete git.{key}; refusing unknown identity"
            )


def _reject_nulls(value: Any, path: str = "$") -> None:
    if value is None:
        raise RuntimeError(f"Rust run-context must not contain null: {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_nulls(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_nulls(item, f"{path}[{index}]")


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
        "backend_version": "resolved-by-rust-runtime",
        "provider_id": config.provider.id,
        "provider_ort_name": config.provider.ort_name,
        "provider_available": False,
    }
    _apply_runtime_overrides(
        context,
        strict_provider=args.strict_provider,
        optimization_level=args.optimization_level,
    )
    _require_concrete_git_identity(context)
    _normalize_rust_only_optionals(context)
    _reject_nulls(context)

    # The shared schema remains a compatibility floor; Rust applies the stronger
    # no-null/type/invariant contract again when the evaluator starts.
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
