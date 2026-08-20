"""
Model-specific feature extraction.

Boundary:

    CanonicalAudio
        |
        +-- Parakeet / NeMo frontend
        |
        +-- Whisper frontend
        |
        +-- future model frontend

Feature extraction is deliberately separated from generic audio
canonicalization.

The project MUST NOT invent frontend parameters for Parakeet.
Parameters are resolved from the pinned upstream model configuration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from parakeet_onnx.config import ModelConfig

from .resample import (
    CANONICAL_SAMPLE_RATE,
    CanonicalAudio,
)

Float32Array = npt.NDArray[np.float32]
Int64Array = npt.NDArray[np.int64]


class FeatureExtractionError(RuntimeError):
    """Raised when model frontend feature extraction fails."""


@dataclass(frozen=True, slots=True)
class FeatureOutput:
    """
    Backend-neutral output of model frontend processing.

    features:
        float32 tensor.

    length:
        int64 tensor containing valid feature-frame length.

    Layout is model-specific and declared by ``layout``.

    Typical Parakeet/NeMo representation:

        features:
            [batch, feature_bins, frames]

        length:
            [batch]
    """

    features: Float32Array
    length: Int64Array

    layout: str

    frontend_id: str

    def validate(self) -> None:
        if self.features.dtype != np.float32:
            raise FeatureExtractionError("Frontend features must use float32.")

        if self.length.dtype != np.int64:
            raise FeatureExtractionError("Frontend length must use int64.")

        if self.features.ndim < 2:
            raise FeatureExtractionError("Feature tensor rank is unexpectedly low.")

        if self.length.ndim != 1:
            raise FeatureExtractionError("Feature length tensor must have shape [batch].")

        if not np.all(np.isfinite(self.features)):
            raise FeatureExtractionError("Feature tensor contains NaN or infinity.")

        if np.any(self.length < 0):
            raise FeatureExtractionError("Feature length contains negative values.")


class FeatureExtractor(ABC):
    """
    Model-independent feature extractor interface.

    A future Rust frontend should implement the same logical contract.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        pass

    @abstractmethod
    def extract(
        self,
        audio: CanonicalAudio,
    ) -> FeatureOutput:
        pass


class NemoFeatureExtractor(FeatureExtractor):
    """
    NeMo-compatible frontend.

    This implementation intentionally delegates the canonical reference
    frontend to the actual pinned NeMo model/preprocessor.

    It is used to:

    - generate reference features
    - validate future standalone Python frontend implementations
    - validate future Rust frontend implementations

    The production ONNX path may eventually replace this implementation
    with a dependency-light standalone frontend after parity is proven.
    """

    def __init__(
        self,
        preprocessor: Any,
    ) -> None:
        self._preprocessor = preprocessor

    @property
    def id(self) -> str:
        return "nemo-reference"

    def extract(
        self,
        audio: CanonicalAudio,
    ) -> FeatureOutput:
        audio.validate()

        if audio.sample_rate_hz != CANONICAL_SAMPLE_RATE:
            raise FeatureExtractionError(f"NeMo frontend received non-canonical sample rate: {audio.sample_rate_hz}")

        try:
            import torch
        except ImportError as exc:
            raise FeatureExtractionError("NeMo reference feature extraction requires PyTorch.") from exc

        waveform = torch.from_numpy(audio.waveform).to(dtype=torch.float32)

        # NeMo preprocessors expect batch dimension.
        waveform = waveform.unsqueeze(0)

        length = torch.tensor(
            [audio.num_samples],
            dtype=torch.int64,
        )

        try:
            with torch.inference_mode():
                output = self._preprocessor(
                    input_signal=waveform,
                    length=length,
                )
        except Exception as exc:
            raise FeatureExtractionError(f"NeMo feature extraction failed: {exc}") from exc

        if not isinstance(output, tuple) or len(output) != 2:
            raise FeatureExtractionError(
                "NeMo preprocessor returned an unexpected value. Expected (features, feature_length)."
            )

        features_torch, length_torch = output

        try:
            features = features_torch.detach().cpu().to(dtype=torch.float32).contiguous().numpy()

            feature_length = length_torch.detach().cpu().to(dtype=torch.int64).contiguous().numpy()

        except Exception as exc:
            raise FeatureExtractionError("Failed to convert NeMo frontend output to NumPy.") from exc

        result = FeatureOutput(
            features=np.ascontiguousarray(
                features,
                dtype=np.float32,
            ),
            length=np.ascontiguousarray(
                feature_length,
                dtype=np.int64,
            ),
            layout="batch_feature_frames",
            frontend_id=self.id,
        )

        result.validate()

        return result


class PassthroughWaveformExtractor(FeatureExtractor):
    """
    Adapter for ONNX artifacts that include their own frontend.

    In this mode the ONNX graph consumes canonical waveform directly.

    This extractor mainly exists to make the frontend boundary explicit.
    """

    @property
    def id(self) -> str:
        return "canonical-waveform"

    def extract(
        self,
        audio: CanonicalAudio,
    ) -> FeatureOutput:
        audio.validate()

        # [samples] -> [batch, samples]
        features = np.ascontiguousarray(
            audio.waveform[np.newaxis, :],
            dtype=np.float32,
        )

        length = np.asarray(
            [audio.num_samples],
            dtype=np.int64,
        )

        result = FeatureOutput(
            features=features,
            length=length,
            layout="batch_samples",
            frontend_id=self.id,
        )

        result.validate()

        return result


def create_feature_extractor(
    *,
    model: ModelConfig,
    nemo_preprocessor: Any | None = None,
) -> FeatureExtractor:
    """
    Build the model frontend selected by ModelConfig.

    Parakeet reference path
    -----------------------

        frontend.implementation = "nemo_compatible"

    requires the actual preprocessor resolved from the pinned NeMo model.

    Deployment candidates whose ONNX graph includes the frontend can use
    an explicit "onnx_waveform" implementation.
    """

    implementation = str(model.require("frontend.implementation"))

    if implementation == "nemo_compatible":
        if nemo_preprocessor is None:
            raise FeatureExtractionError(
                "nemo_compatible frontend requires the preprocessor from the pinned NeMo reference model."
            )

        return NemoFeatureExtractor(nemo_preprocessor)

    if implementation == "onnx_waveform":
        return PassthroughWaveformExtractor()

    raise FeatureExtractionError(f"Unsupported frontend implementation: {implementation!r}")
