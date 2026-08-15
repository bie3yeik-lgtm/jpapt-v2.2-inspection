from __future__ import annotations

from pathlib import Path

import numpy as np

from parakeet_onnx.datasets.materializer import DatasetMaterializer
from parakeet_onnx.datasets.models import DatasetRecord


def test_materializer_copies_existing_local_file(
    mono_wav_16k: Path,
    tmp_path: Path,
) -> None:
    record = DatasetRecord(
        identity="path:mono.wav",
        index=0,
        duration_sec=1.0,
        sample_rate_hz=16_000,
        transcription="test",
        audio={"path": str(mono_wav_16k)},
        audio_path=str(mono_wav_16k),
    )

    materializer = DatasetMaterializer(
        tmp_path / "cache"
    )

    result = materializer.materialize(
        record=record,
        dataset_revision="rev-a",
    )

    assert result.path.is_file()
    assert result.path != mono_wav_16k.resolve()
    assert result.size_bytes > 0
    assert len(result.sha256) == 64
    assert result.source_kind == "local_file"


def test_materializer_reuses_verified_cache(
    mono_wav_16k: Path,
    tmp_path: Path,
) -> None:
    record = DatasetRecord(
        identity="path:mono.wav",
        index=0,
        duration_sec=1.0,
        sample_rate_hz=16_000,
        transcription="test",
        audio={"path": str(mono_wav_16k)},
        audio_path=str(mono_wav_16k),
    )

    materializer = DatasetMaterializer(
        tmp_path / "cache"
    )

    first = materializer.materialize(
        record=record,
        dataset_revision="rev-a",
    )
    second = materializer.materialize(
        record=record,
        dataset_revision="rev-a",
    )

    assert first.path == second.path
    assert first.sha256 == second.sha256


def test_materializer_writes_decoded_array(
    tmp_path: Path,
) -> None:
    waveform = np.linspace(
        -0.5,
        0.5,
        16_000,
        dtype=np.float32,
    )

    record = DatasetRecord(
        identity="id:array",
        index=0,
        duration_sec=1.0,
        sample_rate_hz=16_000,
        transcription="test",
        audio={
            "array": waveform,
            "sampling_rate": 16_000,
        },
    )

    materializer = DatasetMaterializer(
        tmp_path / "cache"
    )

    result = materializer.materialize(
        record=record,
        dataset_revision="rev-a",
    )

    assert result.path.suffix == ".wav"
    assert result.source_kind == "decoded_array"
    assert result.path.is_file()
