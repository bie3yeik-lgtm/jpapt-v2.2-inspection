"""
Canonical audio processing boundary.

Pipeline:

    ResolvedDatasetSample
        -> decode_audio_sample()
        -> DecodedAudio
        -> to_canonical_audio()
        -> CanonicalAudio
        -> feature extractor

Canonical waveform contract:

    dtype:
        numpy.float32

    shape:
        [num_samples]

    channels:
        mono

    sample rate:
        16000 Hz by default

    amplitude:
        normalized floating-point PCM, nominally [-1.0, 1.0]

This package intentionally does not depend on Hugging Face datasets.
Dataset acquisition/materialization belongs to parakeet_onnx.datasets.
"""

from .decode import (
    AudioDecodeError,
    DecodedAudio,
    decode_audio_file,
    decode_audio_sample,
)
from .features import (
    FeatureExtractionError,
    FeatureExtractor,
    FeatureOutput,
    NemoFeatureExtractor,
    create_feature_extractor,
)
from .resample import (
    CANONICAL_SAMPLE_RATE,
    CanonicalAudio,
    ResampleError,
    mix_to_mono,
    resample_audio,
    to_canonical_audio,
)

__all__ = [
    "AudioDecodeError",
    "CANONICAL_SAMPLE_RATE",
    "CanonicalAudio",
    "DecodedAudio",
    "FeatureExtractionError",
    "FeatureExtractor",
    "FeatureOutput",
    "NemoFeatureExtractor",
    "ResampleError",
    "create_feature_extractor",
    "decode_audio_file",
    "decode_audio_sample",
    "mix_to_mono",
    "resample_audio",
    "to_canonical_audio",
]
