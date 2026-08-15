from __future__ import annotations

import argparse
from pathlib import Path

from parakeet_onnx.config import resolve_config
from parakeet_onnx.datasets import (
    DatasetMaterializer,
    DatasetResolver,
    HuggingFaceDatasetBackend,
)
from parakeet_onnx.decoding import VocabularyTokenizer
from parakeet_onnx.evaluation.pipeline import PythonCtcEvaluator
from parakeet_onnx.evaluation.runner import (
    EvaluationRunInputs,
    run_evaluation,
)
from parakeet_onnx.hf.revisions import load_revision_bundle
from parakeet_onnx.run_context import build_run_context
from parakeet_onnx.runtime import (
    ModelContract,
    OrtCtcRunner,
    OrtSessionConfig,
    create_session,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakeet-onnx-evaluate",
        description="Python-first CTC ONNX evaluation runner.",
    )
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--candidate-id", default=None)
    parser.add_argument("--vocabulary", type=Path, required=True)
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

    materializer_root = Path(
        str(
            config.environment.get(
                "path.materialized_audio_cache",
                ".cache/evaluation/audio",
            )
        )
    )
    materializer = DatasetMaterializer(materializer_root)
    backend = HuggingFaceDatasetBackend(
        cache_dir=config.environment.get(
            "path.huggingface_cache",
            ".cache/huggingface",
        ),
        streaming=False,
    )
    resolver = DatasetResolver(
        dataset_lock=revisions.datasets,
        backend=backend,
        materializer=materializer,
        repository_root=config.repository_root,
    )

    manifest = resolver.resolve(
        config.repository_root / config.evaluation.manifest,
        expected_sample_count=config.evaluation.expected_sample_count,
    )

    contract = ModelContract.load(args.candidate_dir)
    if contract.input_kind == "features":
        raise SystemExit(
            "This CLI cannot construct the canonical NeMo frontend without "
            "the pinned NeMo integration. Use waveform-in-graph candidates "
            "or inject a FeatureExtractor programmatically."
        )

    session = create_session(
        OrtSessionConfig(
            model_path=args.model,
            provider_id=args.provider,
        )
    )
    tokenizer = VocabularyTokenizer.from_json(args.vocabulary)

    context = build_run_context(
        config=config,
        revisions=revisions,
        candidate_path=args.model,
        candidate_id=args.candidate_id,
        artifact_role="primary",
    )

    evaluator = PythonCtcEvaluator(
        run_id=context.run_id,
        runner=OrtCtcRunner(session, contract),
        tokenizer=tokenizer,
        provider_id=args.provider,
    )
    benchmark = run_evaluation(
        evaluator,
        EvaluationRunInputs(
            resolved_manifest=manifest,
            run_context=context,
            output_dir=args.output,
            candidate_id=args.candidate_id,
        ),
    )

    print(f"run_id: {benchmark.run_id}")
    print(f"acceptance.passed: {benchmark.acceptance.passed}")
    print(f"CER: {benchmark.quality.cer}")
    print(f"WER: {benchmark.quality.wer}")
    return 0 if benchmark.acceptance.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
