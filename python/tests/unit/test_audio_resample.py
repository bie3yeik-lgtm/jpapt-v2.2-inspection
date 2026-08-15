from __future__ import annotations

from pathlib import Path

import numpy as np

from parakeet_onnx.audio.decode import decode_audio_file
from parakeet_onnx.audio.resample import (
    CANONICAL_SAMPLE_RATE,
    mix_to_mono,
    to_canonical_audio,
)


def test_mix_to_mono() -> None:
    stereo = np.asarray(
        [
            [1.0, 0.0],
            [0.0, 1.0],
        ],
        dtype=np.float32,
    )

    mono = mix_to_mono(stereo)

    np.testing.assert_allclose(
        mono,
        np.asarray([0.5, 0.5], dtype=np.float32),
    )


def test_to_canonical_audio_from_stereo_48k(
    stereo_wav_48k: Path,
) -> None:
    decoded = decode_audio_file(
        stereo_wav_48k
    )

    canonical = to_canonical_audio(
        decoded
    )

    assert canonical.sample_rate_hz == CANONICAL_SAMPLE_RATE
    assert canonical.waveform.dtype == np.float32
    assert canonical.waveform.ndim == 1
    assert canonical.waveform.flags.c_contiguous
    assert np.all(np.isfinite(canonical.waveform))
    assert abs(canonical.num_samples - 16_000) <= 2
