"""
Audio decoding.

Responsibilities:

- Read an audio file referenced by ResolvedDatasetSample.
- Produce normalized float32 PCM.
- Preserve the source sample rate.
- Preserve channel information.

Non-responsibilities:

- Resampling
- Mono downmix
- Feature extraction
- ASR model-specific normalization

Those operations belong to resample.py and features.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from parakeet_onnx.datasets import ResolvedDatasetSample

Float32Array = npt.NDArray[np.float32]


class AudioDecodeError(RuntimeError):
    """Raised when an evaluation audio file cannot be decoded."""


@dataclass(frozen=True, slots=True)
class DecodedAudio:
    """
    Decoded floating-point PCM before canonicalization.

    waveform layout:

        mono:
            [samples]

        multi-channel:
            [samples, channels]

    The decoder must never return integer PCM.
    """

    waveform: Float32Array
    sample_rate_hz: int
    channels: int

    source_path: str | None = None

    @property
    def num_samples(self) -> int:
        return int(self.waveform.shape[0])

    @property
    def duration_sec(self) -> float:
        if self.sample_rate_hz <= 0:
            return 0.0

        return float(self.num_samples) / float(self.sample_rate_hz)

    def validate(self) -> None:
        if self.sample_rate_hz <= 0:
            raise AudioDecodeError("Decoded audio sample rate must be positive.")

        if self.channels <= 0:
            raise AudioDecodeError("Decoded audio channel count must be positive.")

        if self.waveform.dtype != np.float32:
            raise AudioDecodeError("Decoded waveform must use float32.")

        if self.waveform.ndim not in (1, 2):
            raise AudioDecodeError("Decoded waveform must have shape [samples] or [samples, channels].")

        if self.waveform.shape[0] == 0:
            raise AudioDecodeError("Decoded waveform is empty.")

        actual_channels = 1 if self.waveform.ndim == 1 else int(self.waveform.shape[1])

        if actual_channels != self.channels:
            raise AudioDecodeError(
                "Decoded waveform channel count does not match "
                f"metadata: waveform={actual_channels}, "
                f"metadata={self.channels}"
            )

        if not np.all(np.isfinite(self.waveform)):
            raise AudioDecodeError("Decoded waveform contains NaN or infinity.")


def _decode_with_soundfile(
    path: Path,
) -> DecodedAudio:
    """
    Decode using soundfile/libsndfile.

    soundfile is intentionally isolated behind this function so the
    decoder backend can later be replaced without changing the public
    audio contract.
    """

    try:
        import soundfile as sf
    except ImportError as exc:
        raise AudioDecodeError("Audio decoding requires the 'soundfile' package.") from exc

    try:
        waveform, sample_rate = sf.read(
            str(path),
            dtype="float32",
            always_2d=True,
        )
    except Exception as exc:
        raise AudioDecodeError(f"Failed to decode audio file {path}: {exc}") from exc

    waveform = np.asarray(
        waveform,
        dtype=np.float32,
        order="C",
    )

    channels = int(waveform.shape[1])

    # Keep mono in canonical one-dimensional representation.
    if channels == 1:
        waveform = waveform[:, 0]

    result = DecodedAudio(
        waveform=waveform,
        sample_rate_hz=int(sample_rate),
        channels=channels,
        source_path=path.as_posix(),
    )

    result.validate()

    return result


def decode_audio_file(
    path: str | Path,
) -> DecodedAudio:
    """
    Decode one local audio file.

    The returned waveform is always float32 but is not yet guaranteed to
    be mono or 16 kHz.
    """

    audio_path = Path(path).expanduser().resolve()

    if not audio_path.is_file():
        raise AudioDecodeError(f"Audio file does not exist: {audio_path}")

    return _decode_with_soundfile(audio_path)


def decode_audio_sample(
    sample: ResolvedDatasetSample,
) -> DecodedAudio:
    """
    Decode an evaluation sample.

    Boundary contract
    -----------------

    ResolvedDatasetSample must contain a materialized local ``audio_path``
    before entering the audio layer.

    Hugging Face datasets, remote URLs, Arrow objects, and DatasetRecord
    objects are intentionally not accepted here.
    """

    if not sample.audio_path:
        raise AudioDecodeError(
            "ResolvedDatasetSample has no materialized audio_path: "
            f"sample={sample.id!r}. "
            "Dataset materialization must occur before audio decoding."
        )

    decoded = decode_audio_file(sample.audio_path)

    # This is diagnostic rather than authoritative because the dataset
    # metadata may describe the original asset before materialization.
    if sample.sample_rate_hz is not None and decoded.sample_rate_hz != sample.sample_rate_hz:
        raise AudioDecodeError(
            "Decoded sample rate disagrees with resolved dataset metadata: "
            f"sample={sample.id!r}, "
            f"resolved={sample.sample_rate_hz}, "
            f"decoded={decoded.sample_rate_hz}"
        )

    return decoded
