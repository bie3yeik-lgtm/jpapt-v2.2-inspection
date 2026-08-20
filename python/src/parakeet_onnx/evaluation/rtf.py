"""Strict, framework-independent RTF calculation contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RtfScope = Literal["model", "service"]


@dataclass(frozen=True, slots=True)
class RtfMetrics:
    rtf: float
    rtfx: float
    scope: RtfScope


def calculate_rtf(
    *,
    audio_duration_sec: float,
    processing_duration_sec: float,
    scope: RtfScope = "model",
) -> RtfMetrics:
    """Calculate corpus RTF without silently accepting invalid measurements."""

    if scope not in ("model", "service"):
        raise ValueError(f"Unsupported RTF scope: {scope!r}")
    if not float("-inf") < audio_duration_sec < float("inf"):
        raise ValueError("audio_duration_sec must be finite")
    if not float("-inf") < processing_duration_sec < float("inf"):
        raise ValueError("processing_duration_sec must be finite")
    if audio_duration_sec <= 0:
        raise ValueError("audio_duration_sec must be positive")
    if processing_duration_sec <= 0:
        raise ValueError("processing_duration_sec must be positive")

    rtf = processing_duration_sec / audio_duration_sec
    return RtfMetrics(rtf=rtf, rtfx=1.0 / rtf, scope=scope)
