from __future__ import annotations

from pathlib import Path

import numpy as np

from parakeet_onnx.audio.decode import decode_audio_file


def test_decode_mono_float32(
    mono_wav_16k: Path,
) -> None:
    decoded = decode_audio_file(
        mono_wav_16k
    )

    assert decoded.sample_rate_hz == 16_000
    assert decoded.channels == 1
    assert decoded.waveform.dtype == np.float32
    assert decoded.waveform.ndim == 1
    assert decoded.num_samples == 16_000
