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
            if not isinstance(item, list) or not item or not all(
                isinstance(dim, int) and dim > 0 for dim in item
            ):
                raise CandidateMetadataError(
                    "each predictor.state_shapes entry must be a non-empty positive integer array"
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
        for dtype in dtypes:
            _state_dtype(dtype)

        durations_raw = decoder_raw.get("durations")
        if (
            not isinstance(durations_raw, list)
            or not durations_raw
            or not all(isinstance(value, int) and value >= 0 for value in durations_raw)
        ):
            raise CandidateMetadataError(
                "decoder_config.durations must be a non-empty non-negative integer array"
            )
        if len(set(durations_raw)) != len(durations_raw):
            raise CandidateMetadataError("decoder_config.durations must not contain duplicates")

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
        if output_mode == "concatenated" and (
            token_vocab_size is None or token_vocab_size <= 0
        ):
            raise CandidateMetadataError(
                "joint.token_vocab_size is required and positive for concatenated TDT output"
            )
        if output_mode == "separate" and duration_output is None:
            raise CandidateMetadataError(
                "joint.duration_output is required for separate TDT output"
            )

        max_symbols = int(decoder_raw.get("max_symbols_per_step", 10))
        if max_symbols <= 0:
            raise CandidateMetadataError("max_symbols_per_step must be positive")

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
                max_symbols_per_step=max_symbols,
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
        _require_finite_nonempty(waveform, "TDT waveform input")
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
        if len(encoder_values) != len(encoder_outputs):
            raise RuntimeError(
                "TDT encoder returned an output count that differs from the generated contract"
            )
        encoder = np.asarray(encoder_values[0])
        _require_finite_nonempty(encoder, "TDT encoder output")
        if encoder.ndim == 3 and encoder.shape[0] == 1:
            encoder_frames = encoder[0]
        elif encoder.ndim == 2:
            encoder_frames = encoder
        else:
            raise RuntimeError(
                f"TDT encoder output must be [T,D] or [1,T,D], got {encoder.shape!r}"
            )
        if encoder_frames.shape[0] <= 0 or encoder_frames.shape[-1] <= 0:
            raise RuntimeError(
                f"TDT encoder produced a zero-size frame tensor: {encoder_frames.shape!r}"
            )
        if len(encoder_values) > 1:
            length_value = np.asarray(encoder_values[1])
            if length_value.size != 1:
                raise RuntimeError(
                    "TDT encoder length output must contain exactly one scalar value"
                )
            encoded_length = int(length_value.reshape(-1)[0])
            if not 0 < encoded_length <= encoder_frames.shape[0]:
                raise RuntimeError(
                    "TDT encoder length output is outside the produced frame range: "
                    f"length={encoded_length}, frames={encoder_frames.shape[0]}"
                )
            encoder_frames = encoder_frames[:encoded_length]

        state: tuple[np.ndarray, ...] = tuple(
            np.zeros(shape, dtype=_state_dtype(dtype))
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
            if len(previous) != len(self.contract.io.predictor_state_inputs):
                raise RuntimeError(
                    "TDT predictor state arity changed before predictor invocation"
                )
            predictor_feeds: dict[str, np.ndarray] = {
                self.contract.io.predictor_token_input: np.asarray(
                    [[token_id]], dtype=np.int64
                )
            }
            for index, (name, value) in enumerate(
                zip(self.contract.io.predictor_state_inputs, previous, strict=True)
            ):
                _validate_state(index, value, self.contract)
                predictor_feeds[name] = value
            outputs = [
                self.contract.io.predictor_output,
                *self.contract.io.predictor_state_outputs,
            ]
            started = perf_counter()
            values = self.predictor_session.run(outputs, predictor_feeds)
            ort_decoder_ms += (perf_counter() - started) * 1000.0
            if len(values) != len(outputs):
                raise RuntimeError(
                    "TDT predictor returned an output count that differs from the generated contract"
                )
            prediction = np.asarray(values[0])
            _require_finite_nonempty(prediction, "TDT predictor output")
            next_state = tuple(np.asarray(value) for value in values[1:])
            if len(next_state) != len(self.contract.io.predictor_state_outputs):
                raise RuntimeError("TDT predictor returned an invalid state arity")
            for index, value in enumerate(next_state):
                _validate_state(index, value, self.contract)
            return prediction, next_state

        def joint_step(
            frame: np.ndarray,
            prediction: np.ndarray,
        ) -> tuple[np.ndarray, np.ndarray]:
            nonlocal ort_decoder_ms
            frame_value = np.asarray(frame, dtype=np.float32).reshape(1, 1, -1)
            prediction_value = np.asarray(prediction)
            _require_finite_nonempty(frame_value, "TDT joint encoder input")
            _require_finite_nonempty(prediction_value, "TDT joint predictor input")
            outputs = [self.contract.io.joint_token_output]
            if self.contract.io.joint_duration_output is not None:
                outputs.append(self.contract.io.joint_duration_output)
            started = perf_counter()
            values = self.joint_session.run(
                outputs,
                {
                    self.contract.io.joint_encoder_input: frame_value,
                    self.contract.io.joint_predictor_input: prediction_value,
                },
            )
            ort_decoder_ms += (perf_counter() - started) * 1000.0
            if len(values) != len(outputs):
                raise RuntimeError(
                    "TDT joint returned an output count that differs from the generated contract"
                )
            token_values = np.asarray(values[0]).reshape(-1)
            _require_finite_nonempty(token_values, "TDT joint token output")
            if self.contract.io.joint_output_mode == "concatenated":
                split = int(self.contract.io.token_vocab_size or 0)
                expected = split + len(self.contract.decoder.durations)
                if split <= 0 or token_values.size != expected:
                    raise RuntimeError(
                        "TDT concatenated joint output size does not match token_vocab_size + durations: "
                        f"got={token_values.size}, expected={expected}"
                    )
                return token_values[:split], token_values[split:]
            if len(values) != 2:
                raise RuntimeError("TDT separate joint output requires token and duration tensors")
            duration_values = np.asarray(values[1]).reshape(-1)
            _require_finite_nonempty(duration_values, "TDT joint duration output")
            if duration_values.size != len(self.contract.decoder.durations):
                raise RuntimeError(
                    "TDT duration output size does not match generated duration values: "
                    f"got={duration_values.size}, expected={len(self.contract.decoder.durations)}"
                )
            return token_values, duration_values

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


def _validate_state(index: int, value: np.ndarray, contract: TdtRuntimeContract) -> None:
    expected_shape = contract.io.predictor_state_shapes[index]
    expected_dtype = _state_dtype(contract.io.predictor_state_dtypes[index])
    if tuple(value.shape) != expected_shape:
        raise RuntimeError(
            f"TDT predictor state {index} changed shape: got={value.shape!r}, "
            f"expected={expected_shape!r}"
        )
    if value.dtype != expected_dtype:
        raise RuntimeError(
            f"TDT predictor state {index} changed dtype: got={value.dtype}, "
            f"expected={expected_dtype}"
        )
    _require_finite_nonempty(value, f"TDT predictor state {index}")


def _state_dtype(name: str) -> np.dtype[Any]:
    mapping: dict[str, Any] = {
        "float16": np.float16,
        "float32": np.float32,
        "float64": np.float64,
        "int32": np.int32,
        "int64": np.int64,
    }
    try:
        return np.dtype(mapping[name])
    except KeyError as exc:
        raise CandidateMetadataError(f"unsupported TDT predictor state dtype: {name}") from exc


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
