from __future__ import annotations

import pytest

from parakeet_onnx.evaluation.rtf import calculate_rtf


def test_calculates_corpus_rtf_and_rtfx() -> None:
    result = calculate_rtf(audio_duration_sec=3600.0, processing_duration_sec=180.0)
    assert result.rtf == pytest.approx(0.05)
    assert result.rtfx == pytest.approx(20.0)
    assert result.scope == "model"


@pytest.mark.parametrize(
    ("audio_duration_sec", "processing_duration_sec"),
    [(0.0, 1.0), (float("nan"), 1.0), (1.0, 0.0), (1.0, float("inf"))],
)
def test_rejects_invalid_measurements(audio_duration_sec: float, processing_duration_sec: float) -> None:
    with pytest.raises(ValueError):
        calculate_rtf(
            audio_duration_sec=audio_duration_sec,
            processing_duration_sec=processing_duration_sec,
        )
