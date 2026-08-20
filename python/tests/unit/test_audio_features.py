from __future__ import annotations

import numpy as np

from parakeet_onnx.audio.features import PassthroughWaveformExtractor
from parakeet_onnx.audio.resample import CanonicalAudio


def test_passthrough_waveform_extractor() -> None:
    waveform = np.zeros(
        16_000,
        dtype=np.float32,
    )

    audio = CanonicalAudio(waveform=waveform)

    extractor = PassthroughWaveformExtractor()
    output = extractor.extract(audio)

    assert output.features.shape == (1, 16_000)
    assert output.length.tolist() == [16_000]
    assert output.layout == "batch_samples"
