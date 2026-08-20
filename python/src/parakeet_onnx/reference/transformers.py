"""Transformers-based canonical ASR reference support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


class TransformersReferenceError(RuntimeError):
    """Raised when a Transformers ASR reference cannot be loaded or executed."""


@dataclass(frozen=True, slots=True)
class TransformersReferenceOutput:
    text: str
    token_ids: tuple[int, ...]


class TransformersSpeechSeq2SeqReference:
    """
    Pinned Transformers speech-seq2seq reference.

    The model and processor/tokenizer identities are independent because the
    canonical reference contract pins them separately in reference.json.
    """

    def __init__(
        self,
        *,
        model: Any,
        processor: Any,
        device: str,
        language: str,
        task: str,
    ) -> None:
        self.model = model
        self.processor = processor
        self.device = device
        self.language = language
        self.task = task

    @classmethod
    def from_pretrained(
        cls,
        *,
        model_repo_id: str,
        model_revision: str,
        tokenizer_repo_id: str,
        tokenizer_revision: str,
        device: str = "cpu",
        language: str = "ja",
        task: str = "transcribe",
    ) -> TransformersSpeechSeq2SeqReference:
        for name, value in (
            ("model_repo_id", model_repo_id),
            ("model_revision", model_revision),
            ("tokenizer_repo_id", tokenizer_repo_id),
            ("tokenizer_revision", tokenizer_revision),
        ):
            if not value:
                raise TransformersReferenceError(f"{name} must not be empty.")

        try:
            from transformers import (
                AutoModelForSpeechSeq2Seq,
                AutoProcessor,
            )
        except ImportError as exc:
            raise TransformersReferenceError(
                "Transformers reference support requires the optional 'transformers' dependencies."
            ) from exc

        try:
            processor = AutoProcessor.from_pretrained(
                tokenizer_repo_id,
                revision=tokenizer_revision,
            )
            model = AutoModelForSpeechSeq2Seq.from_pretrained(
                model_repo_id,
                revision=model_revision,
            )
            model = model.to(device)
            model.eval()
        except Exception as exc:
            raise TransformersReferenceError(f"Failed to load pinned Transformers ASR reference: {exc}") from exc

        return cls(
            model=model,
            processor=processor,
            device=device,
            language=language,
            task=task,
        )

    def transcribe(
        self,
        waveform: np.ndarray,
        *,
        sample_rate_hz: int = 16000,
    ) -> TransformersReferenceOutput:
        value = np.asarray(waveform, dtype=np.float32)

        if value.ndim != 1:
            raise TransformersReferenceError("Transformers reference input must be a mono 1-D waveform.")
        if value.size == 0:
            raise TransformersReferenceError("Transformers reference input must not be empty.")
        if sample_rate_hz <= 0:
            raise TransformersReferenceError("sample_rate_hz must be positive.")
        if not np.all(np.isfinite(value)):
            raise TransformersReferenceError("Transformers reference input contains NaN or infinity.")

        try:
            import torch

            inputs = self.processor(
                value,
                sampling_rate=sample_rate_hz,
                return_tensors="pt",
            )

            input_features = getattr(inputs, "input_features", None)
            if input_features is None:
                raise TransformersReferenceError(
                    "Processor did not return input_features required by speech-seq2seq generation."
                )

            input_features = input_features.to(self.device)

            with torch.inference_mode():
                generated = self.model.generate(
                    input_features,
                    language=self.language,
                    task=self.task,
                )

            token_ids = tuple(int(item) for item in generated[0].detach().cpu().tolist())
            text = self.processor.batch_decode(
                generated,
                skip_special_tokens=True,
            )[0]

        except TransformersReferenceError:
            raise
        except Exception as exc:
            raise TransformersReferenceError(f"Transformers ASR reference execution failed: {exc}") from exc

        return TransformersReferenceOutput(
            text=str(text),
            token_ids=token_ids,
        )
