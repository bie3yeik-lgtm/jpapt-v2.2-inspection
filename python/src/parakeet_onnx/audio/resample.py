"""
Canonical waveform normalization.

Canonical ASR waveform contract:

    dtype:
        float32

    shape:
        [num_samples]

    channels:
        1

    sample rate:
        16000 Hz

    numeric representation:
        normalized PCM floating point

    contiguous memory:
        yes

The same contract should later be reproduced by the Rust implementation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .decode import DecodedAudio


Float32Array = npt.NDArray[np.float32]


CANONICAL_SAMPLE_RATE = 16_000


class ResampleError(RuntimeError):
    """Raised when waveform canonicalization fails."""


@dataclass(frozen=True, slots=True)
class CanonicalAudio:
    """
    Model-independent canonical ASR waveform.

    This is the formal boundary between generic audio processing and
    model-specific feature extraction.
    """

    waveform: Float32Array
    sample_rate_hz: int = CANONICAL_SAMPLE_RATE

    source_sample_rate_hz: int | None = None
    source_channels: int | None = None

    @property
    def num_samples(self) -> int:
        return int(
            self.waveform.shape[0]
        )

    @property
    def duration_sec(self) -> float:
        return (
            float(self.num_samples)
            / float(self.sample_rate_hz)
        )

    def validate(self) -> None:
        if self.sample_rate_hz != CANONICAL_SAMPLE_RATE:
            raise ResampleError(
                "Canonical audio must use "
                f"{CANONICAL_SAMPLE_RATE} Hz."
            )

        if self.waveform.dtype != np.float32:
            raise ResampleError(
                "Canonical waveform must be float32."
            )

        if self.waveform.ndim != 1:
            raise ResampleError(
                "Canonical waveform must be mono with shape [samples]."
            )

        if self.waveform.size == 0:
            raise ResampleError(
                "Canonical waveform is empty."
            )

        if not self.waveform.flags.c_contiguous:
            raise ResampleError(
                "Canonical waveform must be C-contiguous."
            )

        if not np.all(
            np.isfinite(self.waveform)
        ):
            raise ResampleError(
                "Canonical waveform contains NaN or infinity."
            )


def mix_to_mono(
    waveform: Float32Array,
) -> Float32Array:
    """
    Convert [samples] or [samples, channels] PCM to mono.

    Multi-channel policy:
        arithmetic mean across channels.

    This policy must remain identical in the Rust implementation.
    """

    value = np.asarray(
        waveform,
        dtype=np.float32,
    )

    if value.ndim == 1:
        return np.ascontiguousarray(
            value,
            dtype=np.float32,
        )

    if value.ndim != 2:
        raise ResampleError(
            "Waveform must have shape [samples] "
            "or [samples, channels]."
        )

    if value.shape[1] <= 0:
        raise ResampleError(
            "Waveform has no audio channels."
        )

    mono = np.mean(
        value,
        axis=1,
        dtype=np.float32,
    )

    return np.ascontiguousarray(
        mono,
        dtype=np.float32,
    )


def _resample_with_scipy(
    waveform: Float32Array,
    *,
    source_rate_hz: int,
    target_rate_hz: int,
) -> Float32Array:
    """
    Polyphase resampling.

    This backend is deterministic for a fixed SciPy version and provides
    a clear algorithm that can later be parity-tested against Rust.
    """

    try:
        from scipy.signal import resample_poly
    except ImportError as exc:
        raise ResampleError(
            "Resampling requires the 'scipy' package."
        ) from exc

    from math import gcd

    divisor = gcd(
        source_rate_hz,
        target_rate_hz,
    )

    up = (
        target_rate_hz
        // divisor
    )

    down = (
        source_rate_hz
        // divisor
    )

    try:
        output = resample_poly(
            waveform,
            up=up,
            down=down,
        )
    except Exception as exc:
        raise ResampleError(
            "Failed to resample audio from "
            f"{source_rate_hz} Hz to {target_rate_hz} Hz: {exc}"
        ) from exc

    return np.ascontiguousarray(
        output,
        dtype=np.float32,
    )


def resample_audio(
    waveform: Float32Array,
    *,
    source_rate_hz: int,
    target_rate_hz: int = CANONICAL_SAMPLE_RATE,
) -> Float32Array:
    """
    Resample one mono float32 waveform.
    """

    if source_rate_hz <= 0:
        raise ResampleError(
            "source_rate_hz must be positive."
        )

    if target_rate_hz <= 0:
        raise ResampleError(
            "target_rate_hz must be positive."
        )

    value = np.asarray(
        waveform,
        dtype=np.float32,
    )

    if value.ndim != 1:
        raise ResampleError(
            "resample_audio expects a mono waveform."
        )

    if value.size == 0:
        raise ResampleError(
            "Cannot resample an empty waveform."
        )

    if source_rate_hz == target_rate_hz:
        return np.ascontiguousarray(
            value,
            dtype=np.float32,
        )

    return _resample_with_scipy(
        value,
        source_rate_hz=source_rate_hz,
        target_rate_hz=target_rate_hz,
    )


def _sanitize_amplitude(
    waveform: Float32Array,
) -> Float32Array:
    """
    Enforce valid floating-point PCM boundaries.

    This does NOT peak-normalize recordings.

    Values slightly outside [-1, 1] can arise from DSP/resampling, so the
    canonical representation clips rather than changing global gain.
    """

    value = np.asarray(
        waveform,
        dtype=np.float32,
    )

    if not np.all(
        np.isfinite(value)
    ):
        raise ResampleError(
            "Waveform contains NaN or infinity."
        )

    value = np.clip(
        value,
        -1.0,
        1.0,
    )

    return np.ascontiguousarray(
        value,
        dtype=np.float32,
    )


def to_canonical_audio(
    decoded: DecodedAudio,
    *,
    target_sample_rate_hz: int = CANONICAL_SAMPLE_RATE,
) -> CanonicalAudio:
    """
    Convert decoded audio into the project-wide canonical waveform.

    Operation order is intentionally fixed:

        decode
        -> channel downmix
        -> resample
        -> finite/amplitude sanitation
        -> contiguous float32

    Python and Rust implementations must preserve this ordering.
    """

    decoded.validate()

    mono = mix_to_mono(
        decoded.waveform
    )

    resampled = resample_audio(
        mono,
        source_rate_hz=decoded.sample_rate_hz,
        target_rate_hz=target_sample_rate_hz,
    )

    sanitized = _sanitize_amplitude(
        resampled
    )

    result = CanonicalAudio(
        waveform=sanitized,
        sample_rate_hz=target_sample_rate_hz,
        source_sample_rate_hz=(
            decoded.sample_rate_hz
        ),
        source_channels=decoded.channels,
    )

    result.validate()

    return result
