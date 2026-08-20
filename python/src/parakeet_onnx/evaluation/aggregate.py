from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from statistics import mean, median
from typing import Iterable

from .metrics import CorpusErrorAccumulator
from .rtf import calculate_rtf
from .models import (
    ComponentTimingSummary,
    ErrorSummary,
    MemorySummary,
    NumericSummary,
    ParitySummary,
    PerformanceSummary,
    ProviderSummary,
    QualitySummary,
    SampleResult,
    SampleSummary,
    TimingDistribution,
)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def _mean_optional(values: Iterable[float | None]) -> float | None:
    materialized = [float(v) for v in values if v is not None]
    return mean(materialized) if materialized else None


@dataclass(frozen=True, slots=True)
class AggregateResult:
    samples: SampleSummary
    quality: QualitySummary
    performance: PerformanceSummary
    memory: MemorySummary
    parity: ParitySummary
    provider: ProviderSummary
    errors: ErrorSummary


def aggregate_sample_results(
    results: list[SampleResult],
    *,
    expected_sample_count: int,
    requested_provider: str,
) -> AggregateResult:
    successful = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status == "failed"]
    skipped = [r for r in results if r.status == "skipped"]

    corpus = CorpusErrorAccumulator()
    for result in successful:
        corpus = corpus.add(
            result.sample.reference_text,
            result.output.text,
        )

    total_audio = sum(r.sample.audio_duration_sec for r in results)
    total_ms = sum(
        r.timing.total_ms or 0.0
        for r in successful
    )
    rtf_metrics = (
        calculate_rtf(
            audio_duration_sec=total_audio,
            processing_duration_sec=total_ms / 1000.0,
            scope="model",
        )
        if total_audio > 0 and total_ms > 0
        else None
    )

    per_sample_ms = [
        r.timing.total_ms
        for r in successful
        if r.timing.total_ms is not None
    ]

    text_values = [
        r.parity.text_match
        for r in successful
        if r.parity.text_match is not None
    ]
    token_values = [
        r.parity.token_match
        for r in successful
        if r.parity.token_match is not None
    ]

    error_counter: Counter[str] = Counter()
    fatal = 0
    for result in results:
        for error in result.errors:
            error_counter[error.code] += 1
            if error.fatal:
                fatal += 1

    providers = [r.provider for r in results]
    registered_values = [
        p.registered for p in providers if p.registered is not None
    ]
    fallback_values = [
        p.fallback_detected
        for p in providers
        if p.fallback_detected is not None
    ]

    return AggregateResult(
        samples=SampleSummary(
            expected=expected_sample_count,
            attempted=len(results),
            successful=len(successful),
            failed=len(failed),
            skipped=len(skipped),
            total_audio_duration_sec=total_audio,
        ),
        quality=QualitySummary(cer=corpus.cer, wer=corpus.wer),
        performance=PerformanceSummary(
            load_ms=None,
            session_creation_ms=None,
            total_processing_ms=total_ms if successful else None,
            rtf=rtf_metrics.rtf if rtf_metrics else None,
            per_sample=TimingDistribution(
                mean_ms=mean(per_sample_ms) if per_sample_ms else None,
                median_ms=median(per_sample_ms) if per_sample_ms else None,
                p50_ms=_percentile(per_sample_ms, 0.50),
                p95_ms=_percentile(per_sample_ms, 0.95),
                p99_ms=_percentile(per_sample_ms, 0.99),
                min_ms=min(per_sample_ms) if per_sample_ms else None,
                max_ms=max(per_sample_ms) if per_sample_ms else None,
            ),
            components=ComponentTimingSummary(
                audio_decode_ms=_mean_optional(
                    r.timing.audio_decode_ms for r in successful
                ),
                resample_ms=_mean_optional(
                    r.timing.resample_ms for r in successful
                ),
                frontend_ms=_mean_optional(
                    r.timing.frontend_ms for r in successful
                ),
                encoder_ms=_mean_optional(
                    r.timing.encoder_ms for r in successful
                ),
                decoder_ms=_mean_optional(
                    r.timing.decoder_ms for r in successful
                ),
                postprocess_ms=_mean_optional(
                    r.timing.postprocess_ms for r in successful
                ),
                inference_ms=_mean_optional(
                    r.timing.inference_ms for r in successful
                ),
            ),
            rtfx=rtf_metrics.rtfx if rtf_metrics else None,
            rtf_scope=rtf_metrics.scope if rtf_metrics else None,
            audio_hours_per_gpu_hour=rtf_metrics.rtfx if rtf_metrics else None,
        ),
        memory=MemorySummary(
            peak_ram_mb=max(
                (
                    r.memory.peak_ram_mb
                    for r in results
                    if r.memory.peak_ram_mb is not None
                ),
                default=None,
            ),
            peak_device_memory_mb=max(
                (
                    r.memory.peak_device_memory_mb
                    for r in results
                    if r.memory.peak_device_memory_mb is not None
                ),
                default=None,
            ),
        ),
        parity=ParitySummary(
            reference_run_id=None,
            text_matches=sum(v is True for v in text_values),
            text_mismatches=sum(v is False for v in text_values),
            token_matches=sum(v is True for v in token_values),
            token_mismatches=sum(v is False for v in token_values),
            text_match_rate=(
                sum(v is True for v in text_values) / len(text_values)
                if text_values else None
            ),
            token_match_rate=(
                sum(v is True for v in token_values) / len(token_values)
                if token_values else None
            ),
            numeric=NumericSummary(),
        ),
        provider=ProviderSummary(
            requested=requested_provider,
            registered=(
                all(registered_values) if registered_values else None
            ),
            execution_proven=None,
            fallback_detected=(
                any(fallback_values) if fallback_values else None
            ),
            fallback_only=None,
            assigned_nodes=None,
            fallback_nodes=None,
        ),
        errors=ErrorSummary(
            total=sum(error_counter.values()),
            fatal=fatal,
            by_code=dict(sorted(error_counter.items())),
        ),
    )
