from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from parakeet_onnx.datasets.models import ResolvedDatasetSample, ResolvedManifest
from parakeet_onnx.evaluation.aggregate import aggregate_sample_results
from parakeet_onnx.evaluation.models import (
    AcceptanceSummary,
    BenchmarkResult,
    CandidateIdentity,
    EvaluationIdentity,
    RuntimeIdentity,
    SampleResult,
)
from parakeet_onnx.evaluation.writer import BenchmarkWriter, SampleResultWriter
from parakeet_onnx.run_context.models import RunContext


class SampleEvaluator(Protocol):
    def evaluate_sample(self, sample: ResolvedDatasetSample) -> SampleResult: ...


@dataclass(frozen=True, slots=True)
class EvaluationRunInputs:
    resolved_manifest: ResolvedManifest
    run_context: RunContext
    output_dir: Path
    candidate_id: str | None
    decoder: str
    candidate_bundle_sha256: str | None = None
    candidate_bundle_size_bytes: int | None = None


def run_evaluation(
    evaluator: SampleEvaluator,
    inputs: EvaluationRunInputs,
) -> BenchmarkResult:
    inputs.output_dir.mkdir(parents=True, exist_ok=True)

    run_context_path = inputs.output_dir / "run-context.json"
    inputs.run_context.write_json(run_context_path)

    results = []
    with SampleResultWriter(inputs.output_dir / "samples.jsonl") as writer:
        for sample in inputs.resolved_manifest.samples:
            result = evaluator.evaluate_sample(sample)
            writer.write(result)
            results.append(result)

    aggregate = aggregate_sample_results(
        results,
        expected_sample_count=inputs.resolved_manifest.expected_sample_count,
        requested_provider=inputs.run_context.provider_id,
    )

    revisions = inputs.run_context.revisions
    evaluation_revision = revisions["evaluation_schema"]
    reference_revision = revisions["reference"]
    dataset_revision = revisions["datasets"]

    acceptance_passed = (
        aggregate.samples.failed == 0
        and aggregate.samples.successful == aggregate.samples.expected
        and aggregate.errors.fatal == 0
    )
    artifact_sha256 = (
        inputs.candidate_bundle_sha256 or inputs.run_context.artifact.sha256
    )
    artifact_size_bytes = (
        inputs.candidate_bundle_size_bytes
        if inputs.candidate_bundle_size_bytes is not None
        else inputs.run_context.artifact.size_bytes
    )

    benchmark = BenchmarkResult.create(
        run_id=inputs.run_context.run_id,
        candidate=CandidateIdentity(
            candidate_id=inputs.candidate_id,
            model_id=inputs.run_context.model_id,
            artifact_sha256=artifact_sha256,
            artifact_size_bytes=artifact_size_bytes,
            decoder=inputs.decoder,  # type: ignore[arg-type]
        ),
        evaluation=EvaluationIdentity(
            suite=inputs.run_context.evaluation_id,  # type: ignore[arg-type]
            manifest=inputs.resolved_manifest.manifest_path,
            expected_sample_count=inputs.resolved_manifest.expected_sample_count,
            reference_revision_sha256=reference_revision["document_sha256"],
            evaluation_schema_sha256=evaluation_revision["document_sha256"],
            datasets_lock_sha256=dataset_revision["document_sha256"],
            revision_bundle_sha256=revisions["bundle_sha256"],
        ),
        runtime=RuntimeIdentity(
            implementation="python",
            backend="onnxruntime",
            backend_version=inputs.run_context.runtime.backend_version,
            environment_id=inputs.run_context.environment_id,  # type: ignore[arg-type]
            provider_id=inputs.run_context.provider_id,  # type: ignore[arg-type]
            provider_ort_name=inputs.run_context.runtime.provider_ort_name,
            os=inputs.run_context.host.os,
            architecture=inputs.run_context.host.architecture,
        ),
        samples=aggregate.samples,
        quality=aggregate.quality,
        performance=aggregate.performance,
        memory=aggregate.memory,
        parity=aggregate.parity,
        provider=aggregate.provider,
        acceptance=AcceptanceSummary(
            passed=acceptance_passed,
            quality_passed=None,
            parity_passed=None,
            provider_passed=None,
            performance_passed=None,
            failed_checks=[] if acceptance_passed else ["sample_execution"],
            warnings=[
                "Threshold-based release acceptance is not yet applied; "
                "evaluation-schema.json remains authoritative."
            ],
        ),
        errors=aggregate.errors,
    )

    BenchmarkWriter(inputs.output_dir / "metrics.json").write(benchmark)
    return benchmark
