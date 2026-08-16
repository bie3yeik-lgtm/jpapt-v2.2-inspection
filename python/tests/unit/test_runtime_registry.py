from __future__ import annotations

import hashlib
import json
from pathlib import Path

from parakeet_onnx.runtime import CandidateArtifacts, registered_decoders
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract


def _artifact(root: Path, name: str) -> dict[str, object]:
    path = root / name
    path.write_bytes(name.encode("utf-8"))
    return {
        "path": name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def test_registry_contains_all_python_decoder_adapters() -> None:
    assert registered_decoders() == ("ctc", "tdt", "whisper_autoregressive")


def test_tdt_runtime_contract_validates_without_ort_sessions(tmp_path: Path) -> None:
    (tmp_path / "vocabulary.json").write_text('["<blank>", "a"]', encoding="utf-8")
    metadata = {
        "schema_version": 2,
        "candidate_id": "tdt-000002",
        "decoder": "tdt",
        "artifact_contract": "tdt-multi-graph-v1",
        "artifacts": {
            "encoder": _artifact(tmp_path, "encoder.onnx"),
            "predictor": _artifact(tmp_path, "predictor.onnx"),
            "joint": _artifact(tmp_path, "joint.onnx"),
        },
        "runtime_contract": {
            "decoder": "tdt",
            "input_kind": "canonical_waveform",
            "io": {
                "encoder": {
                    "input": "audio",
                    "length_input": "audio_length",
                    "output": "encoded",
                    "length_output": "encoded_length",
                },
                "predictor": {
                    "token_input": "token",
                    "output": "prediction",
                    "state_inputs": ["h_in"],
                    "state_outputs": ["h_out"],
                    "state_shapes": [[1, 1, 64]],
                    "state_dtypes": ["float32"],
                },
                "joint": {
                    "encoder_input": "encoder_frame",
                    "predictor_input": "prediction",
                    "token_output": "token_logits",
                    "duration_output": "duration_logits",
                    "output_mode": "separate",
                },
            },
            "decoder_config": {
                "blank_id": 0,
                "bos_id": 1,
                "durations": [0, 1, 2, 4],
                "max_symbols_per_step": 10,
            },
        },
        "tokenizer": {"kind": "vocabulary", "path": "vocabulary.json"},
        "features": {
            "kv_cache": False,
            "multi_graph": True,
            "transformers_processor": False,
            "external_frontend": False,
            "timestamps": False,
        },
    }
    (tmp_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    candidate = CandidateArtifacts.load(tmp_path)
    validate_candidate_runtime_contract(candidate)
