from __future__ import annotations

from pathlib import Path

import numpy as np

from parakeet_onnx.audio import (
    decode_audio_file,
    to_canonical_audio,
)
from parakeet_onnx.datasets.materializer import DatasetMaterializer
from parakeet_onnx.datasets.models import DatasetRecord


def test_materialized_dataset_audio_to_canonical_waveform(
    stereo_wav_48k: Path,
    tmp_path: Path,
) -> None:
    record = DatasetRecord(
        identity="path:stereo.wav",
        index=0,
        duration_sec=1.0,
        sample_rate_hz=48_000,
        transcription="統合テスト",
        audio={"path": str(stereo_wav_48k)},
        audio_path=str(stereo_wav_48k),
    )

    materialized = DatasetMaterializer(tmp_path / ".cache" / "evaluation" / "audio").materialize(
        record=record,
        dataset_revision="dataset-revision-a",
    )

    decoded = decode_audio_file(materialized.path)
    canonical = to_canonical_audio(decoded)

    assert canonical.sample_rate_hz == 16_000
    assert canonical.waveform.dtype == np.float32
    assert canonical.waveform.ndim == 1
    assert abs(canonical.duration_sec - 1.0) < 0.01
