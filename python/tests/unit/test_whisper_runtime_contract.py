from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError
from parakeet_onnx.runtime.whisper import WhisperRuntimeContract


def _artifact(path: Path) -> dict[str, object]:
    path.write_bytes(path.name.encode("utf-8"))
    return {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _candidate(root: Path, *, mismatched_cache: bool = False) -> CandidateArtifacts:
    processor = root / "tokenizer"
    processor.mkdir()
    artifacts = {
        "encoder": _artifact(root / "encoder.onnx"),
        "decoder": _artifact(root / "decoder.onnx"),
        "decoder_with_past": _artifact(root / "decoder_with_past.onnx"),
    }
    initial_outputs = ["present.0.key", "present.0.value"]
    past_inputs = ["past.0.key"] if mismatched_cache else ["past.0.key", "past.0.value"]
    metadata = {
        "schema_version": 2,
        "candidate_id": "whisper-candidate-000002",
        "decoder": "whisper_autoregressive",
        "artifact_contract": "whisper-autoregressive-v1",
        "artifacts": artifacts,
        "runtime_contract": {
            "decoder": "whisper_autoregressive",
            "input_kind": "features",
            "io": {
                "encoder": {
                    "input": "input_features",
                    "output": "last_hidden_state",
                },
                "decoder": {
                    "input_ids": "input_ids",
                    "encoder_hidden_states": "encoder_hidden_states",
                    "logits_output": "logits",
                    "past_outputs": initial_outputs,
                },
                "decoder_with_past": {
                    "input_ids": "input_ids",
                    "encoder_hidden_states": "encoder_hidden_states",
                    "logits_output": "logits",
                    "past_inputs": past_inputs,
                    "past_outputs": ["present.0.key", "present.0.value"],
                },
            },
            "decoder_config": {
                "prompt_token_ids": [50258, 50266, 50360],
                "eos_token_id": 50257,
                "max_new_tokens": 64,
                "suppress_tokens": [1, 2],
                "skip_special_tokens": True,
                "timestamps": False,
            },
        },
        "tokenizer": {"kind": "transformers_processor", "path": "tokenizer"},
        "features": {
            "kv_cache": True,
            "multi_graph": True,
            "transformers_processor": True,
            "external_frontend": True,
            "timestamps": False,
        },
    }
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return CandidateArtifacts.load(root)


def test_whisper_contract_parses_metadata_defined_cache_io(tmp_path: Path) -> None:
    contract = WhisperRuntimeContract.from_candidate(_candidate(tmp_path))
    assert contract.encoder_input == "input_features"
    assert contract.decoder.past_outputs == ("present.0.key", "present.0.value")
    assert contract.decoder_with_past is not None
    assert contract.decoder_with_past.past_inputs == ("past.0.key", "past.0.value")
    assert contract.prompt_token_ids == (50258, 50266, 50360)
    assert contract.max_new_tokens == 64


def test_whisper_contract_rejects_cache_arity_mismatch(tmp_path: Path) -> None:
    with pytest.raises(CandidateMetadataError, match="past_outputs count"):
        WhisperRuntimeContract.from_candidate(_candidate(tmp_path, mismatched_cache=True))
