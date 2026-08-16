from __future__ import annotations

import argparse
import os
from pathlib import Path

from parakeet_onnx.config import resolve_config
from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.datasets import (
    DatasetMaterializer,
    DatasetResolver,
    HuggingFaceDatasetBackend,
)
from parakeet_onnx.evaluation.factory import (
    EvaluatorBuildRequest,
    create_python_evaluator,
)
from parakeet_onnx.evaluation.runner import EvaluationRunInputs, run_evaluation
from parakeet_onnx.hf.revisions import load_revision_bundle
from parakeet_onnx.run_context import build_run_context
from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError


def _resolve_under_root(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (root / path).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakeet-onnx-evaluate",
        description=(
            "Metadata-driven Python ONNX ASR evaluator. Runtime selection is "
            "resolved from config/asr-catalog.json plus candidate metadata bindings."
        ),
    )
    parser.add_argument("--provider", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument(
        "--runtime-variant",
        default=None,
        help=(
            "Runtime variant key such as ctc, tdt, or whisper. Defaults to "
            "ASR_RUNTIME_VARIANT and then the central profile-set default."
        ),
    )
    parser.add_argument(
        "--candidate-id",
        default=None,
        help="Optional assertion; must match metadata.json when supplied.",
    )
    parser.add_argument("--experiment-id", default=None)
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help=(
            "Deprecated compatibility assertion. Runtime selection no longer uses "
            "this path; candidate metadata artifacts are authoritative."
        ),
    )
    parser.add_argument(
        "--vocabulary",
        type=Path,
        default=None,
        help=(
            "Deprecated compatibility assertion. Canonical schema-v3 candidates "
            "declare tokenizer paths per runtime variant."
        ),
    )
    parser.add_argument("--evaluation", default="smoke")
    parser.add_argument("--environment", default=None)
    parser.add_argument(
        "--model-config",
        default="parakeet-tdt_ctc-0.6b-ja",
    )
    parser.add_argument(
        "--revisions",
        type=Path,
        default=Path(".ci/hf/config/revisions"),
    )
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
    requested_variant = args.runtime_variant or os.environ.get("ASR_RUNTIME_VARIANT")

    expected_decoder = revisions.reference.decoders.default
    selected_variant = requested_variant
    expected_profile_id: str | None = None
    if revisions.runtime is not None:
        catalog = load_repository_catalog(config.repository_root)
        selected_variant, expected_profile_id, expected_decoder = (
            revisions.runtime.resolve_variant(requested_variant, catalog=catalog)
        )

    candidate = CandidateArtifacts.load(
        args.candidate_dir,
        variant=selected_variant,
        repository_root=config.repository_root,
    )

    if args.candidate_id is not None and args.candidate_id != candidate.candidate_id:
        raise SystemExit(
            "candidate ID mismatch: "
            f"argument={args.candidate_id!r}, metadata={candidate.candidate_id!r}"
        )
    if revisions.runtime is not None:
        if candidate.profile_set_id != revisions.runtime.profile_set_id:
            raise SystemExit(
                "candidate/config profile-set mismatch: "
                f"candidate={candidate.profile_set_id!r}, "
                f"config={revisions.runtime.profile_set_id!r}"
            )
        if expected_profile_id is not None and candidate.profile_id != expected_profile_id:
            raise SystemExit(
                "candidate/config runtime-profile mismatch: "
                f"candidate={candidate.profile_id!r}, config={expected_profile_id!r}"
            )
    if candidate.decoder != expected_decoder:
        raise SystemExit(
            "candidate/config decoder mismatch after profile resolution: "
            f"candidate={candidate.decoder!r}, expected={expected_decoder!r}"
        )
    if args.model is not None:
        asserted = args.model.expanduser().resolve()
        artifact_paths = {item.path for item in candidate.artifacts.values()}
        if asserted not in artifact_paths:
            raise SystemExit(
                "deprecated --model assertion is not one of selected variant artifacts: "
                f"{asserted}"
            )
    if args.vocabulary is not None and candidate.schema_version >= 2:
        asserted_vocab = args.vocabulary.expanduser().resolve()
        if candidate.tokenizer is None or candidate.tokenizer.path != asserted_vocab:
            raise SystemExit(
                "deprecated --vocabulary assertion does not match selected variant tokenizer"
            )

    materializer_value = config.environment.get(
        "path.materialized_audio_cache",
        ".cache/evaluation/audio",
    )
    materializer_root = _resolve_under_root(
        config.repository_root,
        str(materializer_value),
    )
    cache_value = config.environment.get(
        "path.huggingface_cache",
        ".cache/huggingface",
    )
    hf_cache = _resolve_under_root(config.repository_root, str(cache_value))

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

    metadata: dict[str, object] = {
        "candidate": candidate.provenance_dict(),
        "runtime_variant": candidate.variant or candidate.decoder,
    }
    if args.candidate_id:
        metadata["requested_candidate_id"] = args.candidate_id
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

    primary = candidate.primary_artifact
    context = build_run_context(
        config=config,
        revisions=revisions,
        candidate_path=primary.path,
        candidate_id=candidate.candidate_id,
        artifact_role=primary.role,
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
                artifact.path.stat().st_size
                for artifact in candidate.artifacts.values()
            ),
        ),
    )

    print(f"run_id: {benchmark.run_id}")
    if experiment_id:
        print(f"experiment_id: {experiment_id}")
    print(f"candidate_id: {candidate.candidate_id}")
    print(f"runtime_variant: {candidate.variant or candidate.decoder}")
    print(f"runtime_profile: {candidate.profile_id or 'legacy'}")
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
