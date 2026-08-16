from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Mapping

import numpy as np

from parakeet_onnx.audio.resample import CanonicalAudio
from parakeet_onnx.decoding.tdt import TdtDecoderConfig, greedy_tdt_decode

from .adapter import RuntimeTranscription
from .artifacts import CandidateArtifacts, CandidateMetadataError


@dataclass(frozen=True, slots=True)
class TdtIoContract:
    encoder_input: str
    encoder_length_input: str | None
    encoder_output: str
    encoder_length_output: str | None
    predictor_token_input: str
    predictor_output: str
    predictor_state_inputs: tuple[str, ...]
    predictor_state_outputs: tuple[str, ...]
    predictor_state_shapes: tuple[tuple[int, ...], ...]
    predictor_state_dtypes: tuple[str, ...]
    joint_encoder_input: str
    joint_predictor_input: str
    joint_token_output: str
    joint_duration_output: str | None
    joint_output_mode: str
    token_vocab_size: int | None


@dataclass(frozen=True, slots=True)
class TdtRuntimeContract:
    input_kind: str
    io: TdtIoContract
    decoder: TdtDecoderConfig

    @classmethod
    def from_candidate(cls, candidate: CandidateArtifacts) -> "TdtRuntimeContract":
        if candidate.decoder != "tdt":
            raise CandidateMetadataError(
                f"TDT contract cannot load decoder {candidate.decoder!r}"
            )
        raw = candidate.runtime_contract
        io_raw = _mapping(raw, "io")
        encoder = _mapping(io_raw, "encoder")
        predictor = _mapping(io_raw, "predictor")
        joint = _mapping(io_raw, "joint")
        decoder_raw = _mapping(raw, "decoder_config")

        state_inputs = _string_tuple(predictor.get("state_inputs", []), "state_inputs")
        state_outputs = _string_tuple(predictor.get("state_outputs", []), "state_outputs")
        if len(state_inputs) != len(state_outputs):
            raise CandidateMetadataError(
                "predictor state_inputs and state_outputs must have equal length"
            )
        shapes_raw = predictor.get("state_shapes", [])
        if not isinstance(shapes_raw, list):
            raise CandidateMetadataError("predictor.state_shapes must be an array")
        state_shapes: list[tuple[int, ...]] = []
        for item in shapes_raw:
            if not isinstance(item, list) or not all(
                isinstance(dim, int) and dim >= 0 for dim in item
            ):
                raise CandidateMetadataError(
                    "each predictor.state_shapes entry must be an integer array"
                )
            state_shapes.append(tuple(item))
        if state_inputs and len(state_shapes) != len(state_inputs):
            raise CandidateMetadataError(
                "predictor.state_shapes must describe every state input"
            )
        dtypes = _string_tuple(
            predictor.get("state_dtypes", ["float32"] * len(state_inputs)),
            "state_dtypes",
        )
        if len(dtypes) != len(state_inputs):
            raise CandidateMetadataError(
                "predictor.state_dtypes must describe every state input"
            )

        durations_raw = decoder_raw.get("durations")
        if not isinstance(durations_raw, list) or not all(
            isinstance(value, int) for value in durations_raw
        ):
            raise CandidateMetadataError("decoder_config.durations must be an integer array")

        duration_output = _optional_string(joint, "duration_output")
        output_mode = str(joint.get("output_mode", "separate"))
        if output_mode not in {"separate", "concatenated"}:
            raise CandidateMetadataError(
                "joint.output_mode must be 'separate' or 'concatenated'"
            )
        token_vocab_size_value = joint.get("token_vocab_size")
        token_vocab_size = (
            int(token_vocab_size_value)
            if token_vocab_size_value is not None
            else None
        )
        if output_mode == "concatenated" and not token_vocab_size:
            raise CandidateMetadataError(
                "joint.token_vocab_size is required for concatenated TDT output"
            )
        if output_mode == "separate" and duration_output is None:
            raise CandidateMetadataError(
                "joint.duration_output is required for separate TDT output"
            )

        return cls(
            input_kind=str(raw.get("input_kind", "canonical_waveform")),
            io=TdtIoContract(
                encoder_input=_string(encoder, "input"),
                encoder_length_input=_optional_string(encoder, "length_input"),
                encoder_output=_string(encoder, "output"),
                encoder_length_output=_optional_string(encoder, "length_output"),
                predictor_token_input=_string(predictor, "token_input"),
                predictor_output=_string(predictor, "output"),
                predictor_state_inputs=state_inputs,
                predictor_state_outputs=state_outputs,
                predictor_state_shapes=tuple(state_shapes),
                predictor_state_dtypes=dtypes,
                joint_encoder_input=_string(joint, "encoder_input"),
                joint_predictor_input=_string(joint, "predictor_input"),
                joint_token_output=_string(joint, "token_output"),
                joint_duration_output=duration_output,
                joint_output_mode=output_mode,
                token_vocab_size=token_vocab_size,
            ),
            decoder=TdtDecoderConfig(
                blank_id=int(decoder_raw["blank_id"]),
                bos_id=int(decoder_raw["bos_id"]),
                durations=tuple(int(value) for value in durations_raw),
                max_symbols_per_step=int(
                    decoder_raw.get("max_symbols_per_step", 10)
                ),
            ),
        )


class OrtTdtRuntimeAdapter:
    decoder_id = "tdt"

    def __init__(
        self,
        *,
        candidate: CandidateArtifacts,
        encoder_session: Any,
        predictor_session: Any,
        joint_session: Any,
        tokenizer: object,
    ) -> None:
        self.candidate = candidate
        self.contract = TdtRuntimeContract.from_candidate(candidate)
        self.encoder_session = encoder_session
        self.predictor_session = predictor_session
        self.joint_session = joint_session
        self.tokenizer = tokenizer

    def transcribe(self, audio: CanonicalAudio) -> RuntimeTranscription:
        if self.contract.input_kind != "canonical_waveform":
            raise RuntimeError(
                "TDT candidate requires external features. Export a waveform-in-graph "
                "TDT candidate or provide a model-specific frontend adapter before "
                "enabling this candidate contract."
            )

        waveform = np.ascontiguousarray(audio.waveform[np.newaxis, :], dtype=np.float32)
        feeds: dict[str, np.ndarray] = {self.contract.io.encoder_input: waveform}
        if self.contract.io.encoder_length_input is not None:
            feeds[self.contract.io.encoder_length_input] = np.asarray(
                [audio.num_samples], dtype=np.int64
            )
        encoder_outputs = [self.contract.io.encoder_output]
        if self.contract.io.encoder_length_output is not None:
            encoder_outputs.append(self.contract.io.encoder_length_output)

        encoder_started = perf_counter()
        encoder_values = self.encoder_session.run(encoder_outputs, feeds)
        encoder_ms = (perf_counter() - encoder_started) * 1000.0
        encoder = np.asarray(encoder_values[0])
        if encoder.ndim == 3 and encoder.shape[0] == 1:
            encoder_frames = encoder[0]
        elif encoder.ndim == 2:
            encoder_frames = encoder
        else:
            raise RuntimeError(
                f"TDT encoder output must be [T,D] or [1,T,D], got {encoder.shape!r}"
            )
        if len(encoder_values) > 1:
            encoded_length = int(np.asarray(encoder_values[1]).reshape(-1)[0])
            encoder_frames = encoder_frames[:encoded_length]

        state: tuple[np.ndarray, ...] = tuple(
            np.zeros(shape, dtype=np.dtype(dtype))
            for shape, dtype in zip(
                self.contract.io.predictor_state_shapes,
                self.contract.io.predictor_state_dtypes,
                strict=True,
            )
        )
        ort_decoder_ms = 0.0

        def predictor_step(
            token_id: int,
            previous: tuple[np.ndarray, ...],
        ) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
            nonlocal ort_decoder_ms
            predictor_feeds: dict[str, np.ndarray] = {
                self.contract.io.predictor_token_input: np.asarray(
                    [[token_id]], dtype=np.int64
                )
            }
            for name, value in zip(
                self.contract.io.predictor_state_inputs, previous, strict=True
            ):
                predictor_feeds[name] = value
            outputs = [self.contract.io.predictor_output, *self.contract.io.predictor_state_outputs]
            started = perf_counter()
            values = self.predictor_session.run(outputs, predictor_feeds)
            ort_decoder_ms += (perf_counter() - started) * 1000.0
            prediction = np.asarray(values[0])
            next_state = tuple(np.asarray(value) for value in values[1:])
            return prediction, next_state

        def joint_step(
            frame: np.ndarray,
            prediction: np.ndarray,
        ) -> tuple[np.ndarray, np.ndarray]:
            nonlocal ort_decoder_ms
            frame_value = np.asarray(frame, dtype=np.float32).reshape(1, 1, -1)
            outputs = [self.contract.io.joint_token_output]
            if self.contract.io.joint_duration_output is not None:
                outputs.append(self.contract.io.joint_duration_output)
            started = perf_counter()
            values = self.joint_session.run(
                outputs,
                {
                    self.contract.io.joint_encoder_input: frame_value,
                    self.contract.io.joint_predictor_input: np.asarray(prediction),
                },
            )
            ort_decoder_ms += (perf_counter() - started) * 1000.0
            token_values = np.asarray(values[0]).reshape(-1)
            if self.contract.io.joint_output_mode == "concatenated":
                split = int(self.contract.io.token_vocab_size or 0)
                return token_values[:split], token_values[split:]
            return token_values, np.asarray(values[1]).reshape(-1)

        decoder_started = perf_counter()
        decoded = greedy_tdt_decode(
            encoder_frames,
            config=self.contract.decoder,
            initial_state=state,
            predictor_step=predictor_step,
            joint_step=joint_step,
        )
        algorithm_ms = (perf_counter() - decoder_started) * 1000.0
        text = _ids_to_text(self.tokenizer, decoded.token_ids)
        return RuntimeTranscription(
            text=text,
            token_ids=decoded.token_ids,
            inference_ms=encoder_ms + ort_decoder_ms,
            encoder_ms=encoder_ms,
            decoder_ms=algorithm_ms,
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


def _ids_to_text(tokenizer: object, token_ids: list[int]) -> str:
    if hasattr(tokenizer, "ids_to_text"):
        return str(tokenizer.ids_to_text(token_ids))  # type: ignore[attr-defined]
    if hasattr(tokenizer, "decode"):
        return str(tokenizer.decode(token_ids))  # type: ignore[attr-defined]
    raise TypeError("Unsupported TDT tokenizer: no ids_to_text/decode method")
