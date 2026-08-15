from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable, Protocol

import numpy as np

from parakeet_onnx.audio import decode_audio_file, to_canonical_audio
from parakeet_onnx.audio.features import FeatureExtractor
from parakeet_onnx.datasets.models import ResolvedDatasetSample
from parakeet_onnx.decoding.ctc import greedy_ctc_ids
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
from parakeet_onnx.runtime.inference import OrtCtcRunner


class TokenTextDecoder(Protocol):
    def ids_to_text(self, token_ids: list[int]) -> str: ...


@dataclass(slots=True)
class PythonCtcEvaluator:
    run_id: str
    runner: OrtCtcRunner
    tokenizer: TokenTextDecoder
    provider_id: str
    feature_extractor: FeatureExtractor | None = None

    def evaluate_sample(
        self,
        sample: ResolvedDatasetSample,
    ) -> SampleResult:
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

            frontend_ms: float | None = None
            if self.runner.contract.input_kind == "canonical_waveform":
                inference = self.runner.run_waveform(canonical)
            else:
                if self.feature_extractor is None:
                    raise RuntimeError(
                        "candidate expects external frontend features, but no "
                        "FeatureExtractor was supplied."
                    )
                started = perf_counter()
                features = self.feature_extractor.extract(canonical)
                frontend_ms = (perf_counter() - started) * 1000.0
                inference = self.runner.run_features(features)

            started = perf_counter()
            logits = inference.logits
            token_ids = greedy_ctc_ids(
                logits[0] if logits.ndim == 3 else logits,
                blank_id=self.runner.contract.blank_id,
            )
            if not isinstance(token_ids, list) or (
                token_ids and isinstance(token_ids[0], list)
            ):
                raise RuntimeError("unexpected batched token result")
            decoder_ms = (perf_counter() - started) * 1000.0

            started = perf_counter()
            text = self.tokenizer.ids_to_text(
                [int(item) for item in token_ids]
            )
            normalized = normalize_text(text)
            postprocess_ms = (perf_counter() - started) * 1000.0

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
                    decoder="ctc",
                    batch_size=1,
                ),
                output=AsrOutput.from_tokens(
                    text=text,
                    normalized_text=normalized,
                    tokens=[int(item) for item in token_ids],
                ),
                quality=QualityMetrics(
                    cer=character_error_rate(sample.transcription, text),
                    wer=word_error_rate(sample.transcription, text),
                ),
                timing=TimingMetrics(
                    audio_decode_ms=decode_ms,
                    resample_ms=resample_ms,
                    frontend_ms=frontend_ms,
                    inference_ms=inference.inference_ms,
                    decoder_ms=decoder_ms,
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
                decoder="ctc",
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
