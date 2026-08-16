from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np

from parakeet_onnx.audio.features import FeatureOutput
from parakeet_onnx.audio.resample import CanonicalAudio

from .model_contract import ModelContract


@dataclass(frozen=True, slots=True)
class InferenceOutput:
    logits: np.ndarray
    inference_ms: float


class OrtCtcRunner:
    def __init__(self, session: Any, contract: ModelContract) -> None:
        self.session = session
        self.contract = contract

    def run_waveform(self, audio: CanonicalAudio) -> InferenceOutput:
        if self.contract.input_kind != "canonical_waveform":
            raise ValueError("candidate expects frontend features, not waveform")

        waveform = np.ascontiguousarray(
            audio.waveform[np.newaxis, :],
            dtype=np.float32,
        )
        _require_finite_nonempty(waveform, "CTC waveform input")
        feeds: dict[str, np.ndarray] = {
            self.contract.primary_input: waveform,
        }
        if self.contract.length_input is not None:
            feeds[self.contract.length_input] = np.asarray(
                [audio.num_samples],
                dtype=np.int64,
            )
        return self._run(feeds)

    def run_features(self, features: FeatureOutput) -> InferenceOutput:
        if self.contract.input_kind != "features":
            raise ValueError("candidate expects canonical waveform, not features")

        primary = np.ascontiguousarray(features.features, dtype=np.float32)
        _require_finite_nonempty(primary, "CTC feature input")
        feeds: dict[str, np.ndarray] = {
            self.contract.primary_input: primary,
        }
        if self.contract.length_input is not None:
            feeds[self.contract.length_input] = np.ascontiguousarray(
                features.length, dtype=np.int64
            )
        return self._run(feeds)

    def _run(self, feeds: dict[str, np.ndarray]) -> InferenceOutput:
        started = perf_counter()
        values = self.session.run(
            [self.contract.logits_output],
            feeds,
        )
        elapsed_ms = (perf_counter() - started) * 1000.0

        if len(values) != 1:
            raise RuntimeError("ORT returned an unexpected output count.")

        logits = np.asarray(values[0])
        if logits.ndim not in (2, 3):
            raise RuntimeError(
                f"CTC logits must have rank 2 or 3, got {logits.shape!r}"
            )
        _require_finite_nonempty(logits, "CTC logits")

        return InferenceOutput(
            logits=logits,
            inference_ms=elapsed_ms,
        )


def _require_finite_nonempty(value: np.ndarray, label: str) -> None:
    if value.size == 0 or any(dimension == 0 for dimension in value.shape):
        raise RuntimeError(f"{label} has a zero-size runtime shape: {value.shape!r}")
    if np.issubdtype(value.dtype, np.floating) and not np.all(np.isfinite(value)):
        raise RuntimeError(f"{label} contains NaN or infinity")
