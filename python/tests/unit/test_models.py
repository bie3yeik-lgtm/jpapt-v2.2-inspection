from __future__ import annotations

import numpy as np
import pytest

from parakeet_onnx.datasets.models import (
    DatasetRecord,
    ManifestFilters,
    ManifestSelection,
)


def test_manifest_selection_validation() -> None:
    ManifestSelection(
        strategy="stable_hash",
        count=1,
        seed="seed",
    ).validate()


def test_manifest_selection_rejects_zero_count() -> None:
    with pytest.raises(ValueError):
        ManifestSelection(
            strategy="stable_hash",
            count=0,
            seed="seed",
        ).validate()


def test_manifest_filters_accepts_boundaries() -> None:
    filters = ManifestFilters(
        min_duration_sec=1.0,
        max_duration_sec=2.0,
    )

    assert filters.accepts(1.0)
    assert filters.accepts(1.5)
    assert not filters.accepts(2.0)
    assert not filters.accepts(0.9)
    assert not filters.accepts(2.1)


def test_dataset_record_validation() -> None:
    record = DatasetRecord(
        identity="id:test",
        index=0,
        duration_sec=1.0,
        sample_rate_hz=16_000,
        transcription="テスト",
        audio=np.zeros(16_000, dtype=np.float32),
    )

    record.validate()
