from __future__ import annotations

import argparse
import os
from pathlib import Path

from parakeet_onnx.config import resolve_config
from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.datasets import DatasetMaterializer, DatasetResolver, HuggingFaceDatasetBackend
from parakeet_onnx.evaluation.factory import EvaluatorBuildRequest, create_python_evaluator
from parakeet_onnx.evaluation.runner import EvaluationRunInputs, run_evaluation
from parakeet_onnx.hf.revisions import load_revision_bundle
from parakeet_onnx.run_context import build_run_context
from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError


def _resolve_under_root(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakeet-onnx-evaluate",
        description="Evaluate a minimal candidate through the strict typed execution contract.",
    )
    parser.add_argument("--provider", required=True, choices=("cpu", "cuda", "directml", "coreml"))
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--runtime-variant")
    parser.add_argument("--candidate-id")
    parser.add_argument("--experiment-id")
    parser.add_argument(
        "--evaluation",
        default="smoke",
        choices=("smoke", "parity", "coreml-parity", "full"),
    )
    parser.add_argument("--environment", choices=("linux", "windows", "macos"))
    parser.add_argument("--model-config", default="parakeet-tdt_ctc-0.6b-ja")
    parser.add_argument("--revisions", type=Path, default=Path(".ci/hf/config/revisions"))
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = resolve_config(
        model=args.model_config,
        provider=args.provider,
        evaluation=args.evaluation,
        environment=args.environment,
    )
    revisions = load_revision_bundle(args.revisions)
    catalog = load_repository_catalog(config.repository_root)
    requested_variant = args.runtime_variant or os.environ.get("ASR_RUNTIME_VARIANT")
    selected_variant, expected_profile_id, expected_decoder = revisions.runtime.resolve_variant(
        requested_variant,
        catalog=catalog,
    )

    candidate = CandidateArtifacts.load(
        args.candidate_dir,
        variant=selected_variant,
        repository_root=config.repository_root,
    )
    if args.candidate_id is not None and args.candidate_id != candidate.candidate_id:
        raise SystemExit(
            "candidate ID mismatch: "
            f"argument={args.candidate_id!r}, resolved={candidate.candidate_id!r}"
        )
    if candidate.profile_set_id != revisions.runtime.profile_set_id:
        raise SystemExit(
            "candidate/config profile-set mismatch: "
            f"candidate={candidate.profile_set_id!r}, config={revisions.runtime.profile_set_id!r}"
        )
    if candidate.profile_id != expected_profile_id:
        raise SystemExit(
            "candidate/config runtime-profile mismatch: "
            f"candidate={candidate.profile_id!r}, config={expected_profile_id!r}"
        )
    if candidate.decoder != expected_decoder:
        raise SystemExit(
            "candidate/config decoder mismatch: "
            f"candidate={candidate.decoder!r}, expected={expected_decoder!r}"
        )

    materializer_root = _resolve_under_root(
        config.repository_root,
        str(config.environment.get("path.materialized_audio_cache", ".cache/evaluation/audio")),
    )
    hf_cache = _resolve_under_root(
        config.repository_root,
        str(config.environment.get("path.huggingface_cache", ".cache/huggingface")),
    )
    resolver = DatasetResolver(
        dataset_lock=revisions.datasets,
        backend=HuggingFaceDatasetBackend(cache_dir=hf_cache, streaming=False),
        materializer=DatasetMaterializer(materializer_root),
        repository_root=config.repository_root,
    )
    manifest = resolver.resolve(
        config.manifest_path,
        expected_sample_count=config.evaluation.expected_sample_count,
    )

    metadata: dict[str, object] = {}
    experiment_id = args.experiment_id or os.environ.get("EXPERIMENT_ID")
    if experiment_id:
        metadata["experiment_id"] = experiment_id
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
        metadata=metadata,
    )
    evaluator = create_python_evaluator(
        EvaluatorBuildRequest(
            run_id=context.run_id,
            provider_id=args.provider,
            candidate=candidate,
        )
    )
    benchmark = run_evaluation(
        evaluator,
        EvaluationRunInputs(
            resolved_manifest=manifest,
            run_context=context,
            output_dir=args.output,
            candidate_id=candidate.candidate_id,
            decoder=candidate.decoder,
            candidate_bundle_sha256=candidate.bundle_sha256,
            candidate_bundle_size_bytes=sum(
                artifact.size_bytes for artifact in candidate.artifacts.values()
            ),
        ),
    )

    print(f"run_id: {benchmark.run_id}")
    if experiment_id:
        print(f"experiment_id: {experiment_id}")
    print(f"candidate_id: {candidate.candidate_id}")
    print(f"runtime_variant: {candidate.variant}")
    print(f"runtime_profile: {candidate.profile_id}")
    print(f"candidate_bundle_sha256: {candidate.bundle_sha256}")
    print(f"decoder: {candidate.decoder}")
    print(f"acceptance.passed: {benchmark.acceptance.passed}")
    print(f"CER: {benchmark.quality.cer}")
    print(f"WER: {benchmark.quality.wer}")
    return 0 if benchmark.acceptance.passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CandidateMetadataError as exc:
        raise SystemExit(f"candidate metadata error: {exc}") from exc
