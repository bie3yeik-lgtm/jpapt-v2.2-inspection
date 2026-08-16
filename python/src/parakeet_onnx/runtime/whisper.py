from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Mapping

import numpy as np

from parakeet_onnx.audio.resample import CanonicalAudio

from .adapter import RuntimeTranscription
from .artifacts import CandidateArtifacts, CandidateMetadataError


@dataclass(frozen=True, slots=True)
class WhisperDecoderIo:
    input_ids: str
    encoder_hidden_states: str | None
    logits_output: str
    past_inputs: tuple[str, ...]
    past_outputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WhisperRuntimeContract:
    encoder_input: str
    encoder_output: str
    decoder: WhisperDecoderIo
    decoder_with_past: WhisperDecoderIo | None
    prompt_token_ids: tuple[int, ...]
    eos_token_id: int
    max_new_tokens: int
    suppress_tokens: tuple[int, ...]
    skip_special_tokens: bool

    @classmethod
    def from_candidate(cls, candidate: CandidateArtifacts) -> "WhisperRuntimeContract":
        if candidate.decoder != "whisper_autoregressive":
            raise CandidateMetadataError(
                f"Whisper contract cannot load decoder {candidate.decoder!r}"
            )
        raw = candidate.runtime_contract
        if str(raw.get("input_kind")) != "features":
            raise CandidateMetadataError(
                "whisper-autoregressive-v1 currently requires input_kind='features'"
            )
        io_raw = _mapping(raw, "io")
        encoder = _mapping(io_raw, "encoder")
        decoder = _decoder_io(_mapping(io_raw, "decoder"), allow_past_inputs=False)
        with_past_raw = io_raw.get("decoder_with_past")
        decoder_with_past = None
        if with_past_raw is not None:
            if not isinstance(with_past_raw, Mapping):
                raise CandidateMetadataError("io.decoder_with_past must be an object")
            decoder_with_past = _decoder_io(with_past_raw, allow_past_inputs=True)
            if len(decoder_with_past.past_inputs) != len(decoder_with_past.past_outputs):
                raise CandidateMetadataError(
                    "decoder_with_past past_inputs/past_outputs must have equal length"
                )
            if decoder.past_outputs and len(decoder.past_outputs) != len(
                decoder_with_past.past_inputs
            ):
                raise CandidateMetadataError(
                    "decoder initial past_outputs count must match decoder_with_past past_inputs"
                )

        generation = _mapping(raw, "decoder_config")
        prompt_raw = generation.get("prompt_token_ids")
        if not isinstance(prompt_raw, list) or not prompt_raw or not all(
            isinstance(value, int) for value in prompt_raw
        ):
            raise CandidateMetadataError(
                "decoder_config.prompt_token_ids must be a non-empty integer array"
            )
        suppress_raw = generation.get("suppress_tokens", [])
        if not isinstance(suppress_raw, list) or not all(
            isinstance(value, int) for value in suppress_raw
        ):
            raise CandidateMetadataError("decoder_config.suppress_tokens must be an integer array")

        return cls(
            encoder_input=_string(encoder, "input"),
            encoder_output=_string(encoder, "output"),
            decoder=decoder,
            decoder_with_past=decoder_with_past,
            prompt_token_ids=tuple(prompt_raw),
            eos_token_id=int(generation["eos_token_id"]),
            max_new_tokens=int(generation.get("max_new_tokens", 448)),
            suppress_tokens=tuple(suppress_raw),
            skip_special_tokens=bool(generation.get("skip_special_tokens", True)),
        )


class OrtWhisperRuntimeAdapter:
    decoder_id = "whisper_autoregressive"

    def __init__(
        self,
        *,
        candidate: CandidateArtifacts,
        encoder_session: Any,
        decoder_session: Any,
        decoder_with_past_session: Any | None,
        processor: Any,
    ) -> None:
        self.candidate = candidate
        self.contract = WhisperRuntimeContract.from_candidate(candidate)
        self.encoder_session = encoder_session
        self.decoder_session = decoder_session
        self.decoder_with_past_session = decoder_with_past_session
        self.processor = processor
        if self.contract.decoder_with_past is not None and decoder_with_past_session is None:
            raise CandidateMetadataError(
                "candidate contract defines decoder_with_past but artifact/session is missing"
            )

    def transcribe(self, audio: CanonicalAudio) -> RuntimeTranscription:
        frontend_started = perf_counter()
        processed = self.processor(
            audio.waveform,
            sampling_rate=audio.sample_rate_hz,
            return_tensors="np",
        )
        try:
            input_features = np.asarray(processed["input_features"], dtype=np.float32)
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                "Transformers processor did not produce input_features"
            ) from exc
        frontend_ms = (perf_counter() - frontend_started) * 1000.0

        encoder_started = perf_counter()
        encoder_values = self.encoder_session.run(
            [self.contract.encoder_output],
            {self.contract.encoder_input: input_features},
        )
        encoder_ms = (perf_counter() - encoder_started) * 1000.0
        hidden = np.asarray(encoder_values[0])

        generated = list(self.contract.prompt_token_ids)
        cache: list[np.ndarray] | None = None
        decoder_ort_ms = 0.0
        decoder_started = perf_counter()
        for _ in range(self.contract.max_new_tokens):
            use_cache = (
                cache is not None
                and self.contract.decoder_with_past is not None
                and self.decoder_with_past_session is not None
            )
            if use_cache:
                io = self.contract.decoder_with_past
                session = self.decoder_with_past_session
                input_ids = np.asarray([[generated[-1]]], dtype=np.int64)
            else:
                io = self.contract.decoder
                session = self.decoder_session
                input_ids = np.asarray([generated], dtype=np.int64)

            feeds: dict[str, np.ndarray] = {io.input_ids: input_ids}
            if io.encoder_hidden_states is not None:
                feeds[io.encoder_hidden_states] = hidden
            if use_cache:
                assert cache is not None
                for name, value in zip(io.past_inputs, cache, strict=True):
                    feeds[name] = value

            output_names = [io.logits_output, *io.past_outputs]
            started = perf_counter()
            values = session.run(output_names, feeds)
            decoder_ort_ms += (perf_counter() - started) * 1000.0
            logits = np.asarray(values[0])
            if logits.ndim < 2:
                raise RuntimeError(f"Whisper logits have invalid shape: {logits.shape!r}")
            next_logits = np.asarray(logits).reshape(-1, logits.shape[-1])[-1].copy()
            for token_id in self.contract.suppress_tokens:
                if 0 <= token_id < next_logits.shape[0]:
                    next_logits[token_id] = -np.inf
            next_token = int(np.argmax(next_logits))
            generated.append(next_token)
            if io.past_outputs:
                cache = [np.asarray(value) for value in values[1:]]
            if next_token == self.contract.eos_token_id:
                break
        decoder_ms = (perf_counter() - decoder_started) * 1000.0

        text_started = perf_counter()
        token_ids = generated[len(self.contract.prompt_token_ids) :]
        tokenizer = getattr(self.processor, "tokenizer", self.processor)
        text = str(
            tokenizer.decode(
                token_ids,
                skip_special_tokens=self.contract.skip_special_tokens,
            )
        )
        postprocess_ms = (perf_counter() - text_started) * 1000.0
        return RuntimeTranscription(
            text=text,
            token_ids=token_ids,
            frontend_ms=frontend_ms,
            encoder_ms=encoder_ms,
            inference_ms=encoder_ms + decoder_ort_ms,
            decoder_ms=decoder_ms,
            postprocess_ms=postprocess_ms,
        )


def _decoder_io(value: Mapping[str, Any], *, allow_past_inputs: bool) -> WhisperDecoderIo:
    past_inputs = _string_tuple(value.get("past_inputs", []), "past_inputs")
    if past_inputs and not allow_past_inputs:
        raise CandidateMetadataError("initial decoder must not define past_inputs")
    return WhisperDecoderIo(
        input_ids=_string(value, "input_ids"),
        encoder_hidden_states=_optional_string(value, "encoder_hidden_states"),
        logits_output=_string(value, "logits_output"),
        past_inputs=past_inputs,
        past_outputs=_string_tuple(value.get("past_outputs", []), "past_outputs"),
    )


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise CandidateMetadataError(f"{key} must be an object")
    return item


def _string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise CandidateMetadataError(f"{key} must be a non-empty string")
    return item


def _optional_string(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item:
        raise CandidateMetadataError(f"{key} must be a non-empty string when present")
    return item


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise CandidateMetadataError(f"{name} must be a string array")
    return tuple(value)
