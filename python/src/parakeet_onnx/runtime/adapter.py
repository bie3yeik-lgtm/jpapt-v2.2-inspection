from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from parakeet_onnx.audio.resample import CanonicalAudio


@dataclass(frozen=True, slots=True)
class RuntimeTranscription:
    text: str
    token_ids: list[int]
    inference_ms: float
    decoder_ms: float
    frontend_ms: float | None = None
    encoder_ms: float | None = None
    postprocess_ms: float | None = None


class AsrRuntimeAdapter(Protocol):
    decoder_id: str

    def transcribe(self, audio: CanonicalAudio) -> RuntimeTranscription: ...
