"""
Typed evaluation result models.

These models map directly to:

    evaluation/schemas/result.schema.json
    evaluation/schemas/benchmark.schema.json

The models intentionally use only JSON-compatible primitive types so that
the same contract can later be implemented in Rust.

No NumPy arrays or framework-specific objects are stored here.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RuntimeImplementation = Literal["python", "rust"]
BackendName = Literal["onnxruntime", "nemo", "transformers"]
ProviderId = Literal["cpu", "cuda", "directml", "coreml"]
DecoderId = Literal["ctc", "tdt", "whisper_autoregressive"]
EvaluationSuite = Literal["smoke", "parity", "coreml-parity", "full"]
SampleStatus = Literal["success", "failed", "skipped"]
ErrorStage = Literal[
    "configuration",
    "dataset",
    "audio_decode",
    "resample",
    "frontend",
    "session_creation",
    "provider_registration",
    "inference",
    "encoder",
    "decoder",
    "postprocess",
    "metrics",
    "parity",
    "output",
]


class JsonModelMixin:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(
        self,
        *,
        indent: int | None = 2,
        sort_keys: bool = True,
    ) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=sort_keys,
        )


@dataclass(frozen=True, slots=True)
class SampleIdentity(JsonModelMixin):
    id: str
    dataset_id: str
    dataset_repo_id: str
    dataset_revision: str
    subset: str | None
    split: str | None
    index: int | None
    audio_sha256: str | None
    audio_duration_sec: float
    sample_rate_hz: int
    reference_text: str


@dataclass(frozen=True, slots=True)
class ExecutionIdentity(JsonModelMixin):
    runtime: RuntimeImplementation
    backend: BackendName
    provider_id: ProviderId
    decoder: DecoderId
    batch_size: int = 1


@dataclass(frozen=True, slots=True)
class AsrOutput(JsonModelMixin):
    text: str
    normalized_text: str
    tokens: list[int]
    token_count: int

    @classmethod
    def from_tokens(
        cls,
        *,
        text: str,
        normalized_text: str,
        tokens: list[int],
    ) -> AsrOutput:
        return cls(
            text=text,
            normalized_text=normalized_text,
            tokens=list(tokens),
            token_count=len(tokens),
        )


@dataclass(frozen=True, slots=True)
class QualityMetrics(JsonModelMixin):
    cer: float | None
    wer: float | None


@dataclass(frozen=True, slots=True)
class TimingMetrics(JsonModelMixin):
    load_ms: float | None = None
    session_creation_ms: float | None = None
    audio_decode_ms: float | None = None
    resample_ms: float | None = None
    frontend_ms: float | None = None
    encoder_ms: float | None = None
    decoder_ms: float | None = None
    postprocess_ms: float | None = None
    inference_ms: float | None = None
    total_ms: float | None = None
    rtf: float | None = None


@dataclass(frozen=True, slots=True)
class MemoryMetrics(JsonModelMixin):
    peak_ram_mb: float | None = None
    peak_device_memory_mb: float | None = None


@dataclass(frozen=True, slots=True)
class TensorComparison(JsonModelMixin):
    compared: bool = False
    passed: bool | None = None
    max_abs_error: float | None = None
    mean_abs_error: float | None = None
    relative_l2: float | None = None

    @classmethod
    def not_compared(cls) -> TensorComparison:
        return cls()


@dataclass(frozen=True, slots=True)
class NumericParity(JsonModelMixin):
    frontend: TensorComparison = field(default_factory=TensorComparison.not_compared)
    encoder: TensorComparison = field(default_factory=TensorComparison.not_compared)
    logits: TensorComparison = field(default_factory=TensorComparison.not_compared)


@dataclass(frozen=True, slots=True)
class ParityResult(JsonModelMixin):
    reference_run_id: str | None
    text_match: bool | None
    token_match: bool | None
    numeric: NumericParity = field(default_factory=NumericParity)

    @classmethod
    def unavailable(cls) -> ParityResult:
        return cls(reference_run_id=None, text_match=None, token_match=None)


@dataclass(frozen=True, slots=True)
class ProviderResult(JsonModelMixin):
    requested: str
    registered: bool | None
    used: bool | None
    fallback_detected: bool | None
    fallback_only: bool | None
    assigned_nodes: int | None
    fallback_nodes: int | None

    @classmethod
    def unknown(cls, requested: str) -> ProviderResult:
        return cls(
            requested=requested,
            registered=None,
            used=None,
            fallback_detected=None,
            fallback_only=None,
            assigned_nodes=None,
            fallback_nodes=None,
        )


@dataclass(frozen=True, slots=True)
class ErrorRecord(JsonModelMixin):
    code: str
    stage: ErrorStage
    message: str
    fatal: bool


@dataclass(frozen=True, slots=True)
class SampleResult(JsonModelMixin):
    schema_version: int
    run_id: str
    sample: SampleIdentity
    execution: ExecutionIdentity
    output: AsrOutput
    quality: QualityMetrics
    timing: TimingMetrics
    memory: MemoryMetrics
    parity: ParityResult
    provider: ProviderResult
    status: SampleStatus
    errors: list[ErrorRecord]

    @classmethod
    def success(
        cls,
        *,
        run_id: str,
        sample: SampleIdentity,
        execution: ExecutionIdentity,
        output: AsrOutput,
        quality: QualityMetrics,
        timing: TimingMetrics,
        memory: MemoryMetrics,
        parity: ParityResult,
        provider: ProviderResult,
    ) -> SampleResult:
        return cls(
            schema_version=1,
            run_id=run_id,
            sample=sample,
            execution=execution,
            output=output,
            quality=quality,
            timing=timing,
            memory=memory,
            parity=parity,
            provider=provider,
            status="success",
            errors=[],
        )


@dataclass(frozen=True, slots=True)
class CandidateIdentity(JsonModelMixin):
    candidate_id: str | None
    model_id: str
    artifact_sha256: str
    artifact_size_bytes: int
    decoder: DecoderId


@dataclass(frozen=True, slots=True)
class EvaluationIdentity(JsonModelMixin):
    suite: EvaluationSuite
    manifest: str
    expected_sample_count: int
    reference_revision_sha256: str
    evaluation_schema_sha256: str
    datasets_lock_sha256: str
    revision_bundle_sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeIdentity(JsonModelMixin):
    implementation: RuntimeImplementation
    backend: BackendName
    backend_version: str | None
    environment_id: Literal["linux", "windows", "macos"]
    provider_id: ProviderId
    provider_ort_name: str
    os: str
    architecture: str


@dataclass(frozen=True, slots=True)
class SampleSummary(JsonModelMixin):
    expected: int
    attempted: int
    successful: int
    failed: int
    skipped: int
    total_audio_duration_sec: float


@dataclass(frozen=True, slots=True)
class QualitySummary(JsonModelMixin):
    cer: float | None
    wer: float | None


@dataclass(frozen=True, slots=True)
class TimingDistribution(JsonModelMixin):
    mean_ms: float | None
    median_ms: float | None
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    min_ms: float | None
    max_ms: float | None


@dataclass(frozen=True, slots=True)
class ComponentTimingSummary(JsonModelMixin):
    audio_decode_ms: float | None
    resample_ms: float | None
    frontend_ms: float | None
    encoder_ms: float | None
    decoder_ms: float | None
    postprocess_ms: float | None
    inference_ms: float | None


@dataclass(frozen=True, slots=True)
class PerformanceSummary(JsonModelMixin):
    load_ms: float | None
    session_creation_ms: float | None
    total_processing_ms: float | None
    rtf: float | None
    per_sample: TimingDistribution
    components: ComponentTimingSummary
    rtfx: float | None = None
    rtf_scope: str | None = None
    audio_hours_per_gpu_hour: float | None = None
    gpu_price_per_hour: float | None = None
    cost_per_audio_hour: float | None = None


@dataclass(frozen=True, slots=True)
class MemorySummary(JsonModelMixin):
    peak_ram_mb: float | None
    peak_device_memory_mb: float | None


@dataclass(frozen=True, slots=True)
class TensorSummary(JsonModelMixin):
    compared_samples: int
    failed_samples: int
    max_abs_error: float | None
    max_mean_abs_error: float | None
    max_relative_l2: float | None

    @classmethod
    def empty(cls) -> TensorSummary:
        return cls(0, 0, None, None, None)


@dataclass(frozen=True, slots=True)
class NumericSummary(JsonModelMixin):
    frontend: TensorSummary = field(default_factory=TensorSummary.empty)
    encoder: TensorSummary = field(default_factory=TensorSummary.empty)
    logits: TensorSummary = field(default_factory=TensorSummary.empty)


@dataclass(frozen=True, slots=True)
class ParitySummary(JsonModelMixin):
    reference_run_id: str | None
    text_matches: int
    text_mismatches: int
    token_matches: int
    token_mismatches: int
    text_match_rate: float | None
    token_match_rate: float | None
    numeric: NumericSummary


@dataclass(frozen=True, slots=True)
class ProviderSummary(JsonModelMixin):
    requested: str
    registered: bool | None
    execution_proven: bool | None
    fallback_detected: bool | None
    fallback_only: bool | None
    assigned_nodes: int | None
    fallback_nodes: int | None


@dataclass(frozen=True, slots=True)
class AcceptanceSummary(JsonModelMixin):
    passed: bool
    quality_passed: bool | None
    parity_passed: bool | None
    provider_passed: bool | None
    performance_passed: bool | None
    failed_checks: list[str]
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class ErrorSummary(JsonModelMixin):
    total: int
    fatal: int
    by_code: dict[str, int]

    @classmethod
    def empty(cls) -> ErrorSummary:
        return cls(total=0, fatal=0, by_code={})


@dataclass(frozen=True, slots=True)
class BenchmarkResult(JsonModelMixin):
    schema_version: int
    run_id: str
    candidate: CandidateIdentity
    evaluation: EvaluationIdentity
    runtime: RuntimeIdentity
    samples: SampleSummary
    quality: QualitySummary
    performance: PerformanceSummary
    memory: MemorySummary
    parity: ParitySummary
    provider: ProviderSummary
    acceptance: AcceptanceSummary
    errors: ErrorSummary

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        candidate: CandidateIdentity,
        evaluation: EvaluationIdentity,
        runtime: RuntimeIdentity,
        samples: SampleSummary,
        quality: QualitySummary,
        performance: PerformanceSummary,
        memory: MemorySummary,
        parity: ParitySummary,
        provider: ProviderSummary,
        acceptance: AcceptanceSummary,
        errors: ErrorSummary,
    ) -> BenchmarkResult:
        return cls(
            schema_version=1,
            run_id=run_id,
            candidate=candidate,
            evaluation=evaluation,
            runtime=runtime,
            samples=samples,
            quality=quality,
            performance=performance,
            memory=memory,
            parity=parity,
            provider=provider,
            acceptance=acceptance,
            errors=errors,
        )
