from __future__ import annotations

import json
from pathlib import Path

import onnx
from onnx import TensorProto, helper
import pytest

from parakeet_onnx.runtime import CandidateArtifacts, registered_decoders
from parakeet_onnx.runtime.artifacts import CandidateMetadataError
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract


ROOT = Path(__file__).resolve().parents[3]


def _save(path: Path, inputs: list[object], outputs: list[object]) -> None:
    onnx.save(helper.make_model(helper.make_graph([], path.stem, inputs, outputs)), path)


def _write_tdt_candidate(tmp_path: Path, *, write_durations: bool = True) -> None:
    (tmp_path / "vocabulary.json").write_text(
        '["<blank>", "<bos>"]\n', encoding="utf-8"
    )
    if write_durations:
        (tmp_path / "model_config.json").write_text(
            json.dumps({"tdt_durations": [0, 1, 2, 3]}) + "\n",
            encoding="utf-8",
        )
    _save(
        tmp_path / "encoder.onnx",
        [
            helper.make_tensor_value_info("audio", TensorProto.FLOAT, [1, "samples"]),
            helper.make_tensor_value_info("audio_length", TensorProto.INT64, [1]),
        ],
        [
            helper.make_tensor_value_info("encoded", TensorProto.FLOAT, [1, "frames", 64]),
            helper.make_tensor_value_info("encoded_length", TensorProto.INT64, [1]),
        ],
    )
    _save(
        tmp_path / "predictor.onnx",
        [
            helper.make_tensor_value_info("token", TensorProto.INT64, [1, 1]),
            helper.make_tensor_value_info("h_in", TensorProto.FLOAT, [1, 1, 64]),
        ],
        [
            helper.make_tensor_value_info("prediction", TensorProto.FLOAT, [1, 1, 64]),
            helper.make_tensor_value_info("h_out", TensorProto.FLOAT, [1, 1, 64]),
        ],
    )
    _save(
        tmp_path / "joint.onnx",
        [
            helper.make_tensor_value_info("encoder_frame", TensorProto.FLOAT, [1, 1, 64]),
            helper.make_tensor_value_info("prediction", TensorProto.FLOAT, [1, 1, 64]),
        ],
        [
            helper.make_tensor_value_info("token_logits", TensorProto.FLOAT, [1, 1, 2]),
            helper.make_tensor_value_info("duration_logits", TensorProto.FLOAT, [1, 1, 4]),
        ],
    )
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {
                "profile_set": "parakeet-tdt-ctc-v1",
                "variants": {
                    "tdt": {
                        "artifacts": {
                            "encoder": "encoder.onnx",
                            "predictor": "predictor.onnx",
                            "joint": "joint.onnx",
                        },
                        "tokenizer": "vocabulary.json",
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_registry_contains_all_python_decoder_adapters() -> None:
    assert registered_decoders() == ("ctc", "tdt", "whisper_autoregressive")


def test_tdt_runtime_contract_is_derived_without_authored_runtime_json(tmp_path: Path) -> None:
    _write_tdt_candidate(tmp_path)

    candidate = CandidateArtifacts.load(tmp_path, variant="tdt", repository_root=ROOT)
    validate_candidate_runtime_contract(candidate)
    assert candidate.runtime_contract["decoder_config"]["blank_id"] == 0
    assert candidate.runtime_contract["decoder_config"]["bos_id"] == 1
    assert candidate.runtime_contract["decoder_config"]["durations"] == [0, 1, 2, 3]
    assert candidate.runtime_contract["io"]["predictor"]["state_shapes"] == [[1, 1, 64]]


def test_tdt_runtime_contract_rejects_missing_exact_durations(tmp_path: Path) -> None:
    _write_tdt_candidate(tmp_path, write_durations=False)

    with pytest.raises(CandidateMetadataError, match="duration values cannot be derived exactly"):
        CandidateArtifacts.load(tmp_path, variant="tdt", repository_root=ROOT)
