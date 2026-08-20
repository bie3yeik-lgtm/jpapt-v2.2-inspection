from __future__ import annotations

import json
from pathlib import Path

import onnx
import pytest
from onnx import TensorProto, helper

from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError
from parakeet_onnx.runtime.whisper import WhisperRuntimeContract

ROOT = Path(__file__).resolve().parents[3]


def _save(path: Path, inputs: list[object], outputs: list[object]) -> None:
    graph = helper.make_graph([], path.stem, inputs, outputs)
    onnx.save(helper.make_model(graph), path)


def _candidate(
    root: Path,
    *,
    mismatched_cache: bool = False,
    auxiliary_inputs: bool = False,
    unknown_auxiliary: bool = False,
) -> CandidateArtifacts:
    processor = root / "tokenizer"
    processor.mkdir()
    (processor / "generation_config.json").write_text(
        json.dumps(
            {
                "decoder_start_token_id": 50258,
                "forced_decoder_ids": [[1, 50266], [2, 50360]],
                "eos_token_id": 50257,
                "max_new_tokens": 64,
                "suppress_tokens": [1, 2],
            }
        ),
        encoding="utf-8",
    )
    (processor / "tokenizer_config.json").write_text("{}\n", encoding="utf-8")

    _save(
        root / "encoder.onnx",
        [helper.make_tensor_value_info("input_features", TensorProto.FLOAT, [1, 80, "frames"])],
        [helper.make_tensor_value_info("last_hidden_state", TensorProto.FLOAT, [1, "frames", 1280])],
    )
    initial_aux = []
    if auxiliary_inputs:
        initial_aux.extend(
            [
                helper.make_tensor_value_info("cache_position", TensorProto.INT64, ["tokens"]),
                helper.make_tensor_value_info("position_ids", TensorProto.INT64, [1, "tokens"]),
                helper.make_tensor_value_info("decoder_attention_mask", TensorProto.INT64, [1, "tokens"]),
            ]
        )
    if unknown_auxiliary:
        initial_aux.append(helper.make_tensor_value_info("mystery_control", TensorProto.INT64, [1]))
    _save(
        root / "decoder.onnx",
        [
            helper.make_tensor_value_info("input_ids", TensorProto.INT64, [1, "tokens"]),
            helper.make_tensor_value_info("encoder_hidden_states", TensorProto.FLOAT, [1, "frames", 1280]),
            *initial_aux,
        ],
        [
            helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, "tokens", 51865]),
            helper.make_tensor_value_info("present.0.key", TensorProto.FLOAT, [1, 20, "tokens", 64]),
            helper.make_tensor_value_info("present.0.value", TensorProto.FLOAT, [1, 20, "tokens", 64]),
        ],
    )
    past_inputs = ["past.0.key"] if mismatched_cache else ["past.0.key", "past.0.value"]
    cached_aux = []
    if auxiliary_inputs:
        cached_aux.extend(
            [
                helper.make_tensor_value_info("cache_position", TensorProto.INT64, [1]),
                helper.make_tensor_value_info("position_ids", TensorProto.INT64, [1, 1]),
                helper.make_tensor_value_info("decoder_attention_mask", TensorProto.INT64, [1, "tokens"]),
            ]
        )
    _save(
        root / "decoder_with_past.onnx",
        [
            helper.make_tensor_value_info("input_ids", TensorProto.INT64, [1, 1]),
            helper.make_tensor_value_info("encoder_hidden_states", TensorProto.FLOAT, [1, "frames", 1280]),
            *cached_aux,
            *[helper.make_tensor_value_info(name, TensorProto.FLOAT, [1, 20, "tokens", 64]) for name in past_inputs],
        ],
        [
            helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 1, 51865]),
            helper.make_tensor_value_info("present.0.key", TensorProto.FLOAT, [1, 20, "tokens", 64]),
            helper.make_tensor_value_info("present.0.value", TensorProto.FLOAT, [1, 20, "tokens", 64]),
        ],
    )
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "profile_set": "whisper-autoregressive-v1",
                "variants": {
                    "whisper": {
                        "artifacts": {
                            "encoder": "encoder.onnx",
                            "decoder": "decoder.onnx",
                            "decoder_with_past": "decoder_with_past.onnx",
                        },
                        "tokenizer": "tokenizer",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return CandidateArtifacts.load(root, repository_root=ROOT)


def test_whisper_contract_is_derived_from_graph_and_generation_config(
    tmp_path: Path,
) -> None:
    contract = WhisperRuntimeContract.from_candidate(_candidate(tmp_path))
    assert contract.encoder_input == "input_features"
    assert contract.decoder.past_outputs == ("present.0.key", "present.0.value")
    assert contract.decoder_with_past is not None
    assert contract.decoder_with_past.past_inputs == ("past.0.key", "past.0.value")
    assert contract.prompt_token_ids == (50258, 50266, 50360)
    assert contract.max_new_tokens == 64


def test_whisper_contract_separates_cache_position_from_kv_cache(
    tmp_path: Path,
) -> None:
    contract = WhisperRuntimeContract.from_candidate(_candidate(tmp_path, auxiliary_inputs=True))
    assert [item.kind for item in contract.decoder.auxiliary_inputs] == [
        "cache_position",
        "position_ids",
        "attention_mask",
    ]
    assert contract.decoder.past_inputs == ()
    assert contract.decoder_with_past is not None
    assert contract.decoder_with_past.past_inputs == ("past.0.key", "past.0.value")
    assert [item.name for item in contract.decoder_with_past.auxiliary_inputs] == [
        "cache_position",
        "position_ids",
        "decoder_attention_mask",
    ]


def test_whisper_contract_rejects_unknown_decoder_control_input(tmp_path: Path) -> None:
    with pytest.raises(CandidateMetadataError, match="neither a supported auxiliary input"):
        _candidate(tmp_path, unknown_auxiliary=True)


def test_whisper_contract_rejects_derived_cache_arity_mismatch(tmp_path: Path) -> None:
    with pytest.raises(CandidateMetadataError, match="past_inputs/past_outputs"):
        WhisperRuntimeContract.from_candidate(_candidate(tmp_path, mismatched_cache=True))
