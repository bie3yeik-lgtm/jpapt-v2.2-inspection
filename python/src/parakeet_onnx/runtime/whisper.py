from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np

from parakeet_onnx.audio.resample import CanonicalAudio

from .adapter import RuntimeTranscription
from .artifacts import CandidateArtifacts, CandidateMetadataError


@dataclass(frozen=True, slots=True)
class WhisperAuxInput:
    name: str
    kind: str
    dtype: str
    rank: int


@dataclass(frozen=True, slots=True)
class WhisperDecoderIo:
    input_ids: str
    encoder_hidden_states: str | None
    logits_output: str
    past_inputs: tuple[str, ...]
    past_outputs: tuple[str, ...]
    auxiliary_inputs: tuple[WhisperAuxInput, ...]


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
    def from_candidate(cls, candidate: CandidateArtifacts) -> WhisperRuntimeContract:
        if candidate.decoder != "whisper_autoregressive":
            raise CandidateMetadataError(f"Whisper contract cannot load decoder {candidate.decoder!r}")
        raw = candidate.runtime_contract
        if str(raw.get("input_kind")) != "features":
            raise CandidateMetadataError("whisper-autoregressive-v1 currently requires input_kind='features'")
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
                raise CandidateMetadataError("decoder_with_past past_inputs/past_outputs must have equal length")
            if decoder.past_outputs and len(decoder.past_outputs) != len(decoder_with_past.past_inputs):
                raise CandidateMetadataError(
                    "decoder initial past_outputs count must match decoder_with_past past_inputs"
                )

        generation = _mapping(raw, "decoder_config")
        prompt_raw = generation.get("prompt_token_ids")
        if (
            not isinstance(prompt_raw, list)
            or not prompt_raw
            or not all(isinstance(value, int) for value in prompt_raw)
        ):
            raise CandidateMetadataError("decoder_config.prompt_token_ids must be a non-empty integer array")
        suppress_raw = generation.get("suppress_tokens", [])
        if not isinstance(suppress_raw, list) or not all(isinstance(value, int) for value in suppress_raw):
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
            raise CandidateMetadataError("candidate contract defines decoder_with_past but artifact/session is missing")

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
            raise RuntimeError("Transformers processor did not produce input_features") from exc
        _require_finite_nonempty(input_features, "Whisper input_features")
        frontend_ms = (perf_counter() - frontend_started) * 1000.0

        encoder_started = perf_counter()
        encoder_values = self.encoder_session.run(
            [self.contract.encoder_output],
            {self.contract.encoder_input: input_features},
        )
        encoder_ms = (perf_counter() - encoder_started) * 1000.0
        if len(encoder_values) != 1:
            raise RuntimeError("Whisper encoder returned an unexpected output count")
        hidden = np.asarray(encoder_values[0])
        _require_finite_nonempty(hidden, "Whisper encoder hidden state")

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
            for auxiliary in io.auxiliary_inputs:
                feeds[auxiliary.name] = _build_auxiliary_input(
                    auxiliary,
                    generated_length=len(generated),
                    input_length=int(input_ids.shape[-1]),
                )
            if use_cache:
                assert cache is not None
                if len(cache) != len(io.past_inputs):
                    raise RuntimeError("Whisper runtime cache arity no longer matches decoder_with_past inputs")
                for name, value in zip(io.past_inputs, cache, strict=True):
                    _require_finite_nonempty(value, f"Whisper past cache {name}")
                    feeds[name] = value

            output_names = [io.logits_output, *io.past_outputs]
            started = perf_counter()
            values = session.run(output_names, feeds)
            decoder_ort_ms += (perf_counter() - started) * 1000.0
            if len(values) != len(output_names):
                raise RuntimeError("Whisper decoder returned an output count that differs from the generated contract")
            logits = np.asarray(values[0])
            if logits.ndim < 2:
                raise RuntimeError(f"Whisper logits have invalid shape: {logits.shape!r}")
            _require_finite_nonempty(logits, "Whisper logits")
            next_logits = logits.reshape(-1, logits.shape[-1])[-1].copy()
            for token_id in self.contract.suppress_tokens:
                if 0 <= token_id < next_logits.shape[0]:
                    next_logits[token_id] = -np.inf
            if not np.any(np.isfinite(next_logits)):
                raise RuntimeError("Whisper token suppression removed every finite logit")
            next_token = int(np.argmax(next_logits))
            generated.append(next_token)

            if io.past_outputs:
                next_cache = [np.asarray(value) for value in values[1:]]
                for name, value in zip(io.past_outputs, next_cache, strict=True):
                    _require_finite_nonempty(value, f"Whisper present cache {name}")
                if cache is not None:
                    _validate_cache_transition(cache, next_cache)
                cache = next_cache
            elif use_cache:
                raise RuntimeError("decoder_with_past consumed cache but did not return replacement cache")

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
        auxiliary_inputs=_auxiliary_inputs(value.get("auxiliary_inputs", [])),
    )


def _auxiliary_inputs(value: object) -> tuple[WhisperAuxInput, ...]:
    if not isinstance(value, list):
        raise CandidateMetadataError("auxiliary_inputs must be an array")
    result: list[WhisperAuxInput] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise CandidateMetadataError("each auxiliary_inputs entry must be an object")
        name = _string(item, "name")
        kind = _string(item, "kind")
        if kind not in {"cache_position", "position_ids", "attention_mask"}:
            raise CandidateMetadataError(f"unsupported Whisper auxiliary input kind: {kind}")
        dtype = _string(item, "dtype")
        rank_raw = item.get("rank")
        if not isinstance(rank_raw, int) or rank_raw not in {1, 2}:
            raise CandidateMetadataError(f"Whisper auxiliary input {name!r} must have rank 1 or 2")
        if kind in {"cache_position", "position_ids"} and dtype not in {
            "int32",
            "int64",
        }:
            raise CandidateMetadataError(f"Whisper {kind} input {name!r} must use int32 or int64")
        result.append(WhisperAuxInput(name=name, kind=kind, dtype=dtype, rank=rank_raw))
    return tuple(result)


def _build_auxiliary_input(
    auxiliary: WhisperAuxInput,
    *,
    generated_length: int,
    input_length: int,
) -> np.ndarray:
    dtype = _numpy_dtype(auxiliary.dtype)
    if auxiliary.kind in {"cache_position", "position_ids"}:
        start = generated_length - input_length
        if start < 0:
            raise RuntimeError("Whisper generated/input lengths produced a negative position")
        value = np.arange(start, generated_length, dtype=dtype)
    elif auxiliary.kind == "attention_mask":
        value = np.ones(generated_length, dtype=dtype)
    else:
        raise RuntimeError(f"unsupported Whisper auxiliary input: {auxiliary.kind}")
    if auxiliary.rank == 2:
        value = value[np.newaxis, :]
    return np.ascontiguousarray(value)


def _numpy_dtype(name: str) -> np.dtype[Any]:
    mapping: dict[str, Any] = {
        "int32": np.int32,
        "int64": np.int64,
        "bool": np.bool_,
        "float16": np.float16,
        "float32": np.float32,
        "float64": np.float64,
    }
    try:
        return np.dtype(mapping[name])
    except KeyError as exc:
        raise CandidateMetadataError(f"unsupported Whisper auxiliary input dtype: {name}") from exc


def _validate_cache_transition(previous: list[np.ndarray], current: list[np.ndarray]) -> None:
    if len(previous) != len(current):
        raise RuntimeError("Whisper cache arity changed between decoder steps")
    for index, (before, after) in enumerate(zip(previous, current, strict=True)):
        if before.ndim != after.ndim:
            raise RuntimeError(f"Whisper cache rank changed at index {index}: {before.shape!r} -> {after.shape!r}")
        if before.shape[0] != after.shape[0]:
            raise RuntimeError(
                f"Whisper cache batch dimension changed at index {index}: {before.shape!r} -> {after.shape!r}"
            )


def _require_finite_nonempty(value: np.ndarray, label: str) -> None:
    if value.size == 0 or any(dimension == 0 for dimension in value.shape):
        raise RuntimeError(f"{label} has a zero-size runtime shape: {value.shape!r}")
    if np.issubdtype(value.dtype, np.floating) and not np.all(np.isfinite(value)):
        raise RuntimeError(f"{label} contains NaN or infinity")


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
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise CandidateMetadataError(f"{name} must be a string array")
    return tuple(value)
