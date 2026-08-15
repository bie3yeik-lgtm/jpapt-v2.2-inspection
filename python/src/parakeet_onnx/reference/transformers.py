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

    This adapter deliberately uses AutoProcessor + AutoModelForSpeechSeq2Seq
    instead of Whisper-specific concrete classes so future compatible
    Transformers ASR models can reuse the same boundary.

    The exact model and processor revision must be supplied by reference.json.
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
        repo_id: str,
        revision: str,
        tokenizer_revision: str | None = None,
        device: str = "cpu",
        language: str = "ja",
        task: str = "transcribe",
    ) -> "TransformersSpeechSeq2SeqReference":
        if not repo_id:
            raise TransformersReferenceError("repo_id must not be empty.")
        if not revision:
            raise TransformersReferenceError(
                "A pinned Transformers model revision is required."
            )

        try:
            from transformers import (
                AutoModelForSpeechSeq2Seq,
                AutoProcessor,
            )
        except ImportError as exc:
            raise TransformersReferenceError(
                "Transformers reference support requires the optional "
                "'transformers' dependencies."
            ) from exc

        processor_revision = tokenizer_revision or revision

        try:
            processor = AutoProcessor.from_pretrained(
                repo_id,
                revision=processor_revision,
            )
            model = AutoModelForSpeechSeq2Seq.from_pretrained(
                repo_id,
                revision=revision,
            )
            model = model.to(device)
            model.eval()
        except Exception as exc:
            raise TransformersReferenceError(
                f"Failed to load pinned Transformers ASR reference: {exc}"
            ) from exc

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
            raise TransformersReferenceError(
                "Transformers reference input must be a mono 1-D waveform."
            )
        if value.size == 0:
            raise TransformersReferenceError(
                "Transformers reference input must not be empty."
            )
        if sample_rate_hz <= 0:
            raise TransformersReferenceError(
                "sample_rate_hz must be positive."
            )
        if not np.all(np.isfinite(value)):
            raise TransformersReferenceError(
                "Transformers reference input contains NaN or infinity."
            )

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
                    "Processor did not return input_features required by "
                    "speech-seq2seq generation."
                )

            input_features = input_features.to(self.device)

            with torch.inference_mode():
                generated = self.model.generate(
                    input_features,
                    language=self.language,
                    task=self.task,
                )

            token_ids = tuple(
                int(item)
                for item in generated[0].detach().cpu().tolist()
            )
            text = self.processor.batch_decode(
                generated,
                skip_special_tokens=True,
            )[0]

        except TransformersReferenceError:
            raise
        except Exception as exc:
            raise TransformersReferenceError(
                f"Transformers ASR reference execution failed: {exc}"
            ) from exc

        return TransformersReferenceOutput(
            text=str(text),
            token_ids=token_ids,
        )
