from __future__ import annotations

import argparse
import os
from pathlib import Path

from parakeet_onnx.config import resolve_config
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
            "Metadata-driven Python ONNX ASR evaluator. Decoder/runtime/artifact "
            "selection is resolved from candidate metadata.json."
        ),
    )
    parser.add_argument("--provider", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument(
        "--candidate-id",
        default=None,
        help="Optional assertion; must match metadata.json when supplied.",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help=(
            "Deprecated compatibility assertion. Runtime selection no longer uses "
            "this path; metadata.json artifacts are authoritative."
        ),
    )
    parser.add_argument(
        "--vocabulary",
        type=Path,
        default=None,
        help=(
            "Deprecated compatibility assertion. Canonical schema-v2 candidates "
            "declare tokenizer/processor assets in metadata.json."
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
    candidate = CandidateArtifacts.load(args.candidate_dir)

    if args.candidate_id is not None and args.candidate_id != candidate.candidate_id:
        raise SystemExit(
            "candidate ID mismatch: "
            f"argument={args.candidate_id!r}, metadata={candidate.candidate_id!r}"
        )
    expected_decoder = revisions.reference.decoders.default
    if candidate.decoder != expected_decoder:
        raise SystemExit(
            "candidate/reference decoder mismatch: "
            f"candidate={candidate.decoder!r}, reference={expected_decoder!r}"
        )
    if args.model is not None:
        asserted = args.model.expanduser().resolve()
        artifact_paths = {item.path for item in candidate.artifacts.values()}
        if asserted not in artifact_paths:
            raise SystemExit(
                "deprecated --model assertion is not one of metadata artifacts: "
                f"{asserted}"
            )
    if args.vocabulary is not None and candidate.schema_version >= 2:
        asserted_vocab = args.vocabulary.expanduser().resolve()
        if candidate.tokenizer is None or candidate.tokenizer.path != asserted_vocab:
            raise SystemExit(
                "deprecated --vocabulary assertion does not match metadata tokenizer"
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
    }
    if args.candidate_id:
        metadata["requested_candidate_id"] = args.candidate_id
    if os.environ.get("EXPERIMENT_ID"):
        metadata["experiment_id"] = os.environ["EXPERIMENT_ID"]
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
        ),
    )

    print(f"run_id: {benchmark.run_id}")
    experiment_id = metadata.get("experiment_id")
    if experiment_id:
        print(f"experiment_id: {experiment_id}")
    print(f"candidate_id: {candidate.candidate_id}")
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
