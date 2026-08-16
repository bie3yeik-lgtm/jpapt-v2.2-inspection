from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_ctc_candidate(root: Path) -> None:
    model = root / "model.onnx"
    model.write_bytes(b"not-a-real-onnx-for-metadata-unit-test")
    vocab = root / "vocabulary.json"
    vocab.write_text('["a", "b", "<blank>"]\n', encoding="utf-8")
    metadata = {
        "schema_version": 2,
        "candidate_id": "ctc-000002",
        "decoder": "ctc",
        "artifact_contract": "ctc-single-graph-v1",
        "artifacts": {
            "primary": {
                "path": "model.onnx",
                "sha256": _sha(model),
                "size_bytes": model.stat().st_size,
            }
        },
        "runtime_contract": {
            "decoder": "ctc",
            "input_kind": "canonical_waveform",
            "io": {
                "primary": {
                    "input": "audio_signal",
                    "length_input": "length",
                    "logits_output": "logits",
                }
            },
            "decoder_config": {"blank_id": 2},
        },
        "tokenizer": {"kind": "vocabulary", "path": "vocabulary.json"},
        "features": {
            "kv_cache": False,
            "multi_graph": False,
            "transformers_processor": False,
            "external_frontend": False,
            "timestamps": False,
        },
    }
    (root / "metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )


def test_loads_schema_v2_candidate_and_bundle_identity(tmp_path: Path) -> None:
    _write_ctc_candidate(tmp_path)
    candidate = CandidateArtifacts.load(tmp_path)
    assert candidate.candidate_id == "ctc-000002"
    assert candidate.decoder == "ctc"
    assert candidate.artifact_contract == "ctc-single-graph-v1"
    assert candidate.primary_artifact.path == tmp_path / "model.onnx"
    assert len(candidate.bundle_sha256) == 64
    assert candidate.provenance_dict()["bundle_sha256"] == candidate.bundle_sha256


def test_rejects_runtime_decoder_mismatch(tmp_path: Path) -> None:
    _write_ctc_candidate(tmp_path)
    path = tmp_path / "metadata.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["runtime_contract"]["decoder"] = "tdt"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(CandidateMetadataError, match="must match"):
        CandidateArtifacts.load(tmp_path, verify_artifacts=False)


def test_rejects_artifact_path_escape(tmp_path: Path) -> None:
    _write_ctc_candidate(tmp_path)
    path = tmp_path / "metadata.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["artifacts"]["primary"]["path"] = "../model.onnx"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(CandidateMetadataError, match="escapes candidate root"):
        CandidateArtifacts.load(tmp_path, verify_artifacts=False)


def test_schema_v1_is_normalized_for_existing_ctc_candidates(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"legacy")
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_id": "legacy-000001",
                "primary_artifact": "model.onnx",
                "decoder": "ctc",
                "artifact_sha256": _sha(model),
                "runtime_contract": {
                    "input_kind": "canonical_waveform",
                    "primary_input": "audio",
                    "length_input": "length",
                    "logits_output": "logits",
                    "blank_id": 0,
                    "decoder": "ctc",
                },
            }
        ),
        encoding="utf-8",
    )
    candidate = CandidateArtifacts.load(tmp_path)
    assert candidate.schema_version == 1
    assert candidate.runtime_contract["io"]["primary"]["input"] == "audio"
