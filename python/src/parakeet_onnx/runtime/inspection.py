from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


class CandidateInspectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TensorInfo:
    name: str
    dtype: str
    shape: tuple[int | None, ...]


@dataclass(frozen=True, slots=True)
class GraphInfo:
    inputs: tuple[TensorInfo, ...]
    outputs: tuple[TensorInfo, ...]
    metadata: Mapping[str, Any]


def inspect_runtime_contract(
    *,
    root: Path,
    decoder: str,
    artifacts: Mapping[str, Path],
    tokenizer_path: Path | None,
) -> dict[str, Any]:
    graphs = {role: _load_graph(path) for role, path in artifacts.items()}
    config = _load_candidate_config(root, tokenizer_path)
    vocabulary = _load_vocabulary(tokenizer_path)
    if decoder == "ctc":
        return _inspect_ctc(graphs, config, vocabulary)
    if decoder == "tdt":
        return _inspect_tdt(graphs, config, vocabulary)
    if decoder == "whisper_autoregressive":
        return _inspect_whisper(graphs, config)
    raise CandidateInspectionError(f"unsupported decoder for inspection: {decoder!r}")


def _load_graph(path: Path) -> GraphInfo:
    try:
        import onnx
    except ImportError as exc:
        raise CandidateInspectionError(
            "candidate inspection requires the project 'onnx' extra"
        ) from exc
    try:
        model = onnx.load(path, load_external_data=False)
    except Exception as exc:
        raise CandidateInspectionError(f"failed to inspect ONNX graph {path}: {exc}") from exc
    initializer_names = {value.name for value in model.graph.initializer}
    inputs = tuple(
        _tensor_info(value)
        for value in model.graph.input
        if value.name not in initializer_names
    )
    outputs = tuple(_tensor_info(value) for value in model.graph.output)
    if not inputs or not outputs:
        raise CandidateInspectionError(f"ONNX graph has no public inputs/outputs: {path}")
    metadata: dict[str, Any] = {}
    for item in model.metadata_props:
        metadata[item.key] = _parse_scalar_or_json(item.value)
    return GraphInfo(inputs=inputs, outputs=outputs, metadata=metadata)


def _tensor_info(value: Any) -> TensorInfo:
    tensor_type = value.type.tensor_type
    dtype = _onnx_dtype_name(int(tensor_type.elem_type))
    dims: list[int | None] = []
    for dim in tensor_type.shape.dim:
        size = int(dim.dim_value)
        dims.append(size if size > 0 else None)
    return TensorInfo(name=str(value.name), dtype=dtype, shape=tuple(dims))


def _onnx_dtype_name(value: int) -> str:
    return {
        1: "float32",
        2: "uint8",
        3: "int8",
        4: "uint16",
        5: "int16",
        6: "int32",
        7: "int64",
        9: "bool",
        10: "float16",
        11: "float64",
        12: "uint32",
        13: "uint64",
        16: "bfloat16",
    }.get(value, f"onnx:{value}")


def _load_candidate_config(root: Path, tokenizer_path: Path | None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    candidates: list[Path] = []
    bases = [root]
    if tokenizer_path is not None and tokenizer_path.is_dir() and tokenizer_path != root:
        bases.append(tokenizer_path)
    for base in bases:
        for name in (
            "config.json",
            "generation_config.json",
            "tokenizer_config.json",
            "preprocessor_config.json",
            "model_config.json",
        ):
            path = base / name
            if path.is_file() and path not in candidates:
                candidates.append(path)
    for path in candidates:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CandidateInspectionError(f"invalid generated config JSON {path}: {exc}") from exc
        if isinstance(raw, Mapping):
            _merge_missing(values, raw)
    return values


def _merge_missing(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if key not in target:
            target[key] = value
        elif isinstance(target[key], dict) and isinstance(value, Mapping):
            _merge_missing(target[key], value)


def _parse_scalar_or_json(value: str) -> Any:
    text = value.strip()
    if not text:
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _load_vocabulary(path: Path | None) -> tuple[str, ...] | None:
    if path is None or not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return tuple(raw)
    if isinstance(raw, Mapping):
        if all(isinstance(key, str) and isinstance(value, int) for key, value in raw.items()):
            if not raw:
                return ()
            result = [""] * (max(int(value) for value in raw.values()) + 1)
            for token, index in raw.items():
                if 0 <= int(index) < len(result):
                    result[int(index)] = token
            return tuple(result)
        if all(str(key).isdigit() and isinstance(value, str) for key, value in raw.items()):
            if not raw:
                return ()
            result = [""] * (max(int(key) for key in raw) + 1)
            for index, token in raw.items():
                result[int(index)] = token
            return tuple(result)
    return None


def _inspect_ctc(
    graphs: Mapping[str, GraphInfo],
    config: Mapping[str, Any],
    vocabulary: tuple[str, ...] | None,
) -> dict[str, Any]:
    graph = _required_graph(graphs, "primary")
    audio = _best_tensor(
        graph.inputs,
        ("audio_signal", "waveform", "audio", "input"),
        prefer_float=True,
    )
    length = _best_tensor(
        tuple(item for item in graph.inputs if item.name != audio.name),
        ("length", "len", "sequence"),
        required=False,
    )
    logits = _best_tensor(
        graph.outputs,
        ("logits", "log_probs", "output"),
        prefer_float=True,
    )
    blank_id = _infer_blank_id((config, graph.metadata), vocabulary)
    primary: dict[str, Any] = {"input": audio.name, "logits_output": logits.name}
    if length is not None:
        primary["length_input"] = length.name
    return {
        "decoder": "ctc",
        "input_kind": "canonical_waveform",
        "io": {"primary": primary},
        "decoder_config": {"blank_id": blank_id},
    }


def _inspect_tdt(
    graphs: Mapping[str, GraphInfo],
    config: Mapping[str, Any],
    vocabulary: tuple[str, ...] | None,
) -> dict[str, Any]:
    encoder = _required_graph(graphs, "encoder")
    predictor = _required_graph(graphs, "predictor")
    joint = _required_graph(graphs, "joint")

    enc_input = _best_tensor(
        encoder.inputs,
        ("audio_signal", "waveform", "audio", "input"),
        prefer_float=True,
    )
    enc_len = _best_tensor(
        tuple(item for item in encoder.inputs if item.name != enc_input.name),
        ("length", "len"),
        required=False,
    )
    enc_output = _best_tensor(
        encoder.outputs,
        ("encoded", "encoder", "output"),
        prefer_float=True,
    )
    enc_out_len = _best_tensor(
        tuple(item for item in encoder.outputs if item.name != enc_output.name),
        ("length", "len"),
        required=False,
    )

    token_input = _best_tensor(
        predictor.inputs,
        ("token", "label", "input_ids", "targets"),
        prefer_integer=True,
    )
    state_inputs = tuple(item for item in predictor.inputs if item.name != token_input.name)
    prediction = _best_tensor(
        predictor.outputs,
        ("prediction", "predictor", "output"),
        prefer_float=True,
    )
    state_outputs = tuple(item for item in predictor.outputs if item.name != prediction.name)
    if len(state_inputs) != len(state_outputs):
        raise CandidateInspectionError(
            "TDT predictor state input/output counts differ; generated contract cannot be inferred"
        )
    state_shapes: list[list[int]] = []
    for state in state_inputs:
        if any(dim is None for dim in state.shape):
            raise CandidateInspectionError(
                f"TDT predictor state {state.name!r} has dynamic dimensions; "
                "export a static state shape or include exact generated state metadata"
            )
        state_shapes.append([int(dim) for dim in state.shape if dim is not None])

    joint_encoder = _best_tensor(joint.inputs, ("encoder", "enc"), prefer_float=True)
    joint_predictor = _best_tensor(
        tuple(item for item in joint.inputs if item.name != joint_encoder.name),
        ("predictor", "prediction", "pred"),
        prefer_float=True,
    )
    duration_output = _best_tensor(joint.outputs, ("duration", "dur"), required=False)
    token_outputs = tuple(
        item for item in joint.outputs if duration_output is None or item.name != duration_output.name
    )
    token_output = _best_tensor(
        token_outputs,
        ("token", "logits", "joint", "output"),
        prefer_float=True,
    )

    sources = (config, predictor.metadata, joint.metadata)
    blank_id = _infer_blank_id(sources, vocabulary)
    bos_id = _find_int_sources(
        sources,
        ("bos_id", "bos_token_id", "decoder_start_token_id"),
    )
    if bos_id is None:
        bos_id = _vocabulary_token_id(vocabulary, ("<bos>", "<s>"))
    if bos_id is None:
        raise CandidateInspectionError(
            "TDT bos_id cannot be derived from generated config, ONNX metadata, or vocabulary"
        )

    durations = _find_int_list_sources(
        sources,
        ("durations", "tdt_durations", "duration_values"),
    )
    if durations is None or not durations:
        raise CandidateInspectionError(
            "TDT duration values cannot be derived exactly; emit durations in generated model config or ONNX metadata"
        )

    output_mode = "separate" if duration_output is not None else "concatenated"
    token_vocab_size: int | None = None
    if output_mode == "concatenated":
        token_vocab_size = _find_int_sources(
            sources,
            ("token_vocab_size", "vocab_size"),
        )
        if token_vocab_size is None or token_vocab_size <= 0:
            raise CandidateInspectionError(
                "concatenated TDT output requires exact token_vocab_size in generated config or ONNX metadata"
            )

    encoder_io: dict[str, Any] = {"input": enc_input.name, "output": enc_output.name}
    if enc_len is not None:
        encoder_io["length_input"] = enc_len.name
    if enc_out_len is not None:
        encoder_io["length_output"] = enc_out_len.name

    predictor_io: dict[str, Any] = {
        "token_input": token_input.name,
        "output": prediction.name,
        "state_inputs": [item.name for item in state_inputs],
        "state_outputs": [item.name for item in state_outputs],
        "state_shapes": state_shapes,
        "state_dtypes": [item.dtype for item in state_inputs],
    }
    joint_io: dict[str, Any] = {
        "encoder_input": joint_encoder.name,
        "predictor_input": joint_predictor.name,
        "token_output": token_output.name,
        "output_mode": output_mode,
    }
    if duration_output is not None:
        joint_io["duration_output"] = duration_output.name
    if token_vocab_size is not None:
        joint_io["token_vocab_size"] = token_vocab_size

    decoder_config: dict[str, Any] = {
        "blank_id": blank_id,
        "bos_id": bos_id,
        "durations": durations,
    }
    max_symbols = _find_int_sources(sources, ("max_symbols_per_step",))
    if max_symbols is not None:
        decoder_config["max_symbols_per_step"] = max_symbols
    return {
        "decoder": "tdt",
        "input_kind": "canonical_waveform",
        "io": {"encoder": encoder_io, "predictor": predictor_io, "joint": joint_io},
        "decoder_config": decoder_config,
    }


def _inspect_whisper(
    graphs: Mapping[str, GraphInfo], config: Mapping[str, Any]
) -> dict[str, Any]:
    encoder = _required_graph(graphs, "encoder")
    decoder = _required_graph(graphs, "decoder")
    encoder_input = _best_tensor(
        encoder.inputs,
        ("input_features", "features", "input"),
        prefer_float=True,
    )
    encoder_output = _best_tensor(
        encoder.outputs,
        ("last_hidden_state", "hidden", "output"),
        prefer_float=True,
    )
    io: dict[str, Any] = {
        "encoder": {"input": encoder_input.name, "output": encoder_output.name},
        "decoder": _inspect_whisper_decoder(decoder, allow_past=False),
    }
    with_past = graphs.get("decoder_with_past")
    if with_past is not None:
        io["decoder_with_past"] = _inspect_whisper_decoder(with_past, allow_past=True)

    prompt = _find_int_list(config, ("prompt_token_ids",))
    if prompt is None:
        prompt = []
        start = _find_int(config, ("decoder_start_token_id", "bos_token_id"))
        if start is not None:
            prompt.append(start)
        forced = _find_value(config, ("forced_decoder_ids",))
        if isinstance(forced, list):
            pairs: list[tuple[int, int]] = []
            for item in forced:
                if (
                    isinstance(item, list)
                    and len(item) == 2
                    and isinstance(item[0], int)
                    and isinstance(item[1], int)
                ):
                    pairs.append((item[0], item[1]))
            for _, token in sorted(pairs):
                if token not in prompt:
                    prompt.append(token)
    if not prompt:
        raise CandidateInspectionError(
            "Whisper prompt token IDs are not present in generated tokenizer/model config"
        )
    eos = _find_int(config, ("eos_token_id",))
    if eos is None:
        raise CandidateInspectionError("Whisper eos_token_id is missing from generated config")
    generation: dict[str, Any] = {
        "prompt_token_ids": prompt,
        "eos_token_id": eos,
        "suppress_tokens": _find_int_list(config, ("suppress_tokens",)) or [],
    }
    max_new_tokens = _find_int(config, ("max_new_tokens",))
    if max_new_tokens is not None:
        generation["max_new_tokens"] = max_new_tokens
    skip_special = _find_value(config, ("skip_special_tokens",))
    if isinstance(skip_special, bool):
        generation["skip_special_tokens"] = skip_special
    return {
        "decoder": "whisper_autoregressive",
        "input_kind": "features",
        "io": io,
        "decoder_config": generation,
    }


def _inspect_whisper_decoder(graph: GraphInfo, *, allow_past: bool) -> dict[str, Any]:
    input_ids = _best_tensor(
        graph.inputs,
        ("input_ids", "tokens", "token"),
        prefer_integer=True,
    )
    encoder_hidden = _best_tensor(
        tuple(item for item in graph.inputs if item.name != input_ids.name),
        ("encoder_hidden_states", "encoder", "hidden"),
        required=False,
    )
    excluded = {input_ids.name}
    if encoder_hidden is not None:
        excluded.add(encoder_hidden.name)

    past_inputs: list[str] = []
    auxiliary_inputs: list[dict[str, Any]] = []
    for item in graph.inputs:
        if item.name in excluded:
  continue
        aux_kind = _whisper_aux_kind(item.name)
        if aux_kind is not None:
  auxiliary_inputs.append(
      {
          "name": item.name,
          "kind": aux_kind,
          "dtype": item.dtype,
          "rank": len(item.shape),
      }
  )
  continue
        if allow_past and _is_whisper_cache_tensor(item.name, past=True):
  past_inputs.append(item.name)
  continue
        raise CandidateInspectionError(
  f"Whisper decoder input {item.name!r} is neither a supported auxiliary input nor an exact past-cache tensor"
        )

    logits = _best_tensor(graph.outputs, ("logits", "output"), prefer_float=True)
    past_outputs: list[str] = []
    for item in graph.outputs:
        if item.name == logits.name:
  continue
        if _is_whisper_cache_tensor(item.name, past=False):
  past_outputs.append(item.name)
  continue
        raise CandidateInspectionError(
  f"Whisper decoder output {item.name!r} is neither logits nor an exact present-cache tensor"
        )

    result: dict[str, Any] = {
        "input_ids": input_ids.name,
        "logits_output": logits.name,
    }
    if encoder_hidden is not None:
        result["encoder_hidden_states"] = encoder_hidden.name
    if auxiliary_inputs:
        result["auxiliary_inputs"] = auxiliary_inputs
    if past_inputs:
        result["past_inputs"] = past_inputs
    if past_outputs:
        result["past_outputs"] = past_outputs
    return result


def _whisper_aux_kind(name: str) -> str | None:
    lowered = name.lower()
    if "cache_position" in lowered:
        return "cache_position"
    if "position_ids" in lowered or lowered.endswith("position_id"):
        return "position_ids"
    if "attention_mask" in lowered:
        return "attention_mask"
    return None


def _is_whisper_cache_tensor(name: str, *, past: bool) -> bool:
    lowered = name.lower()
    if "cache_position" in lowered:
        return False
    markers = ("past", "past_key_values") if past else ("present", "present_key_values")
    if not any(marker in lowered for marker in markers):
        return False
    return any(marker in lowered for marker in ("key", "value", "cache"))

def _infer_blank_id(
    sources: Sequence[Mapping[str, Any]],
    vocabulary: tuple[str, ...] | None,
) -> int:
    value = _find_int_sources(
        sources,
        ("blank_id", "ctc_blank_id", "tdt_blank_id", "blank_index"),
    )
    if value is not None:
        return value
    value = _vocabulary_token_id(
        vocabulary,
        ("<blank>", "<blk>", "<ctc_blank>"),
    )
    if value is not None:
        return value
    raise CandidateInspectionError(
        "blank_id cannot be derived exactly from generated config, ONNX metadata, or an explicit blank token"
    )


def _vocabulary_token_id(
    vocabulary: tuple[str, ...] | None,
    tokens: Sequence[str],
) -> int | None:
    if vocabulary is None:
        return None
    wanted = {token.lower() for token in tokens}
    matches = [
        index for index, token in enumerate(vocabulary) if token.strip().lower() in wanted
    ]
    if len(matches) > 1:
        raise CandidateInspectionError(
            f"vocabulary contains multiple matching special tokens: {matches}"
        )
    return matches[0] if matches else None


def _required_graph(graphs: Mapping[str, GraphInfo], role: str) -> GraphInfo:
    try:
        return graphs[role]
    except KeyError as exc:
        raise CandidateInspectionError(f"missing graph role required for inspection: {role}") from exc


def _best_tensor(
    values: Sequence[TensorInfo],
    keywords: Sequence[str],
    *,
    prefer_float: bool = False,
    prefer_integer: bool = False,
    required: bool = True,
) -> TensorInfo | None:
    if not values:
        if required:
            raise CandidateInspectionError(f"cannot select tensor for keywords={tuple(keywords)!r}")
        return None
    scored: list[tuple[int, TensorInfo]] = []
    for value in values:
        lowered = value.name.lower()
        score = sum(10 for keyword in keywords if keyword in lowered)
        if prefer_float and value.dtype.startswith("float"):
            score += 3
        if prefer_integer and value.dtype.startswith(("int", "uint")):
            score += 3
        scored.append((score, value))
    best_score = max(score for score, _ in scored)
    best = [value for score, value in scored if score == best_score]
    if not required and best_score <= 0:
        return None
    if len(best) != 1:
        raise CandidateInspectionError(
            "tensor binding is ambiguous; "
            f"keywords={tuple(keywords)!r}, candidates={[value.name for value in best]!r}"
        )
    return best[0]


def _find_value(value: Mapping[str, Any], keys: Sequence[str]) -> Any:
    wanted = set(keys)
    queue: list[Mapping[str, Any]] = [value]
    while queue:
        current = queue.pop(0)
        for key, item in current.items():
            if key in wanted and item is not None:
                return item
            if isinstance(item, Mapping):
                queue.append(item)
    return None


def _find_value_sources(
    sources: Sequence[Mapping[str, Any]], keys: Sequence[str]
) -> Any:
    for source in sources:
        value = _find_value(source, keys)
        if value is not None:
            return value
    return None


def _find_int(value: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    item = _find_value(value, keys)
    if isinstance(item, bool):
        return None
    return int(item) if isinstance(item, int) else None


def _find_int_sources(
    sources: Sequence[Mapping[str, Any]], keys: Sequence[str]
) -> int | None:
    item = _find_value_sources(sources, keys)
    if isinstance(item, bool):
        return None
    return int(item) if isinstance(item, int) else None


def _find_int_list(value: Mapping[str, Any], keys: Sequence[str]) -> list[int] | None:
    item = _find_value(value, keys)
    if isinstance(item, list) and all(
        isinstance(entry, int) and not isinstance(entry, bool) for entry in item
    ):
        return [int(entry) for entry in item]
    return None


def _find_int_list_sources(
    sources: Sequence[Mapping[str, Any]], keys: Sequence[str]
) -> list[int] | None:
    item = _find_value_sources(sources, keys)
    if isinstance(item, list) and all(
        isinstance(entry, int) and not isinstance(entry, bool) for entry in item
    ):
        return [int(entry) for entry in item]
    return None
