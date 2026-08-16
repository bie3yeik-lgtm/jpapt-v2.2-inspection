from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from parakeet_onnx.audio import decode_audio_file, to_canonical_audio
from parakeet_onnx.audio.features import FeatureExtractor
from parakeet_onnx.datasets.models import ResolvedDatasetSample
from parakeet_onnx.evaluation.metrics import (
    character_error_rate,
    normalize_text,
    word_error_rate,
)
from parakeet_onnx.evaluation.models import (
    AsrOutput,
    ErrorRecord,
    ExecutionIdentity,
    MemoryMetrics,
    ParityResult,
    ProviderResult,
    QualityMetrics,
    SampleIdentity,
    SampleResult,
    TimingMetrics,
)
from parakeet_onnx.runtime.adapter import AsrRuntimeAdapter
from parakeet_onnx.runtime.ctc import CtcRuntimeAdapter
from parakeet_onnx.runtime.inference import OrtCtcRunner


@dataclass(slots=True)
class PythonAsrEvaluator:
    run_id: str
    adapter: AsrRuntimeAdapter
    provider_id: str

    def evaluate_sample(self, sample: ResolvedDatasetSample) -> SampleResult:
        started_total = perf_counter()
        if sample.audio_path is None:
            return self._failed(
                sample,
                code="MATERIALIZED_AUDIO_MISSING",
                stage="dataset",
                message="Resolved sample has no materialized audio_path.",
            )

        try:
            started = perf_counter()
            decoded = decode_audio_file(Path(sample.audio_path))
            decode_ms = (perf_counter() - started) * 1000.0

            started = perf_counter()
            canonical = to_canonical_audio(decoded)
            resample_ms = (perf_counter() - started) * 1000.0

            output = self.adapter.transcribe(canonical)

            started = perf_counter()
            normalized = normalize_text(output.text)
            normalization_ms = (perf_counter() - started) * 1000.0
            postprocess_ms = (output.postprocess_ms or 0.0) + normalization_ms

            total_ms = (perf_counter() - started_total) * 1000.0
            rtf = (
                total_ms / 1000.0 / canonical.duration_sec
                if canonical.duration_sec > 0
                else None
            )

            return SampleResult.success(
                run_id=self.run_id,
                sample=self._identity(sample, canonical.sample_rate_hz),
                execution=ExecutionIdentity(
                    runtime="python",
                    backend="onnxruntime",
                    provider_id=self.provider_id,  # type: ignore[arg-type]
                    decoder=self.adapter.decoder_id,  # type: ignore[arg-type]
                    batch_size=1,
                ),
                output=AsrOutput.from_tokens(
                    text=output.text,
                    normalized_text=normalized,
                    tokens=output.token_ids,
                ),
                quality=QualityMetrics(
                    cer=character_error_rate(sample.transcription, output.text),
                    wer=word_error_rate(sample.transcription, output.text),
                ),
                timing=TimingMetrics(
                    audio_decode_ms=decode_ms,
                    resample_ms=resample_ms,
                    frontend_ms=output.frontend_ms,
                    encoder_ms=output.encoder_ms,
                    inference_ms=output.inference_ms,
                    decoder_ms=output.decoder_ms,
                    postprocess_ms=postprocess_ms,
                    total_ms=total_ms,
                    rtf=rtf,
                ),
                memory=MemoryMetrics(),
                parity=ParityResult.unavailable(),
                provider=ProviderResult(
                    requested=self.provider_id,
                    registered=True,
                    used=None,
                    fallback_detected=None,
                    fallback_only=None,
                    assigned_nodes=None,
                    fallback_nodes=None,
                ),
            )
        except Exception as exc:
            return self._failed(
                sample,
                code="SAMPLE_EVALUATION_FAILED",
                stage="inference",
                message=str(exc),
            )

    def _identity(
        self,
        sample: ResolvedDatasetSample,
        sample_rate_hz: int,
    ) -> SampleIdentity:
        return SampleIdentity(
            id=sample.id,
            dataset_id=sample.dataset_id,
            dataset_repo_id=sample.dataset_repo_id,
            dataset_revision=sample.dataset_revision,
            subset=sample.subset,
            split=sample.split,
            index=sample.row_index,
            audio_sha256=sample.audio_sha256,
            audio_duration_sec=sample.duration_sec,
            sample_rate_hz=sample_rate_hz,
            reference_text=sample.transcription,
        )

    def _failed(
        self,
        sample: ResolvedDatasetSample,
        *,
        code: str,
        stage: str,
        message: str,
    ) -> SampleResult:
        sample_rate = sample.sample_rate_hz or 16_000
        return SampleResult(
            schema_version=1,
            run_id=self.run_id,
            sample=self._identity(sample, sample_rate),
            execution=ExecutionIdentity(
                runtime="python",
                backend="onnxruntime",
                provider_id=self.provider_id,  # type: ignore[arg-type]
                decoder=self.adapter.decoder_id,  # type: ignore[arg-type]
                batch_size=1,
            ),
            output=AsrOutput.from_tokens(
                text="",
                normalized_text="",
                tokens=[],
            ),
            quality=QualityMetrics(cer=None, wer=None),
            timing=TimingMetrics(),
            memory=MemoryMetrics(),
            parity=ParityResult.unavailable(),
            provider=ProviderResult.unknown(self.provider_id),
            status="failed",
            errors=[
                ErrorRecord(
                    code=code,
                    stage=stage,  # type: ignore[arg-type]
                    message=message,
                    fatal=True,
                )
            ],
        )


@dataclass(slots=True)
class PythonCtcEvaluator:
    """Compatibility wrapper for callers that still construct the CTC pieces.

    New code should construct evaluators through evaluation.factory.
    """

    run_id: str
    runner: OrtCtcRunner
    tokenizer: object
    provider_id: str
    feature_extractor: FeatureExtractor | None = None

    def evaluate_sample(self, sample: ResolvedDatasetSample) -> SampleResult:
        evaluator = PythonAsrEvaluator(
            run_id=self.run_id,
            adapter=CtcRuntimeAdapter(
                runner=self.runner,
                tokenizer=self.tokenizer,
                feature_extractor=self.feature_extractor,
            ),
            provider_id=self.provider_id,
        )
        return evaluator.evaluate_sample(sample)
