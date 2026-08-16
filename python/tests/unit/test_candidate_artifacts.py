from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError


ROOT = Path(__file__).resolve().parents[3]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_ctc_candidate_v3(root: Path) -> None:
    model = root / "model.onnx"
    model.write_bytes(b"not-a-real-onnx-for-metadata-unit-test")
    vocab = root / "vocabulary.json"
    vocab.write_text('["a", "b", "<blank>"]\n', encoding="utf-8")
    catalog = load_repository_catalog(ROOT)
    metadata = {
        "schema_version": 3,
        "candidate_id": "parakeet-candidate-000002",
        "catalog": {
            "id": catalog.catalog_id,
            "sha256": catalog.sha256,
        },
        "profile_set": "parakeet-tdt-ctc-v1",
        "variants": {
            "ctc": {
                "artifacts": {
                    "primary": {
                        "path": "model.onnx",
                        "sha256": _sha(model),
                        "size_bytes": model.stat().st_size,
                    }
                },
                "bindings": {
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
                "tokenizer": {"path": "vocabulary.json"},
            }
        },
    }
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_loads_schema_v3_candidate_and_derives_profile_semantics(tmp_path: Path) -> None:
    _write_ctc_candidate_v3(tmp_path)
    candidate = CandidateArtifacts.load(tmp_path, repository_root=ROOT)
    assert candidate.candidate_id == "parakeet-candidate-000002"
    assert candidate.profile_set_id == "parakeet-tdt-ctc-v1"
    assert candidate.variant == "ctc"
    assert candidate.profile_id == "ctc-v1"
    assert candidate.decoder == "ctc"
    assert candidate.artifact_contract == "ctc-single-graph-v1"
    assert candidate.tokenizer is not None
    assert candidate.tokenizer.kind == "vocabulary"
    assert candidate.primary_artifact.path == tmp_path / "model.onnx"
    assert len(candidate.bundle_sha256) == 64
    provenance = candidate.provenance_dict()
    assert provenance["profile"] == "ctc-v1"
    assert provenance["catalog"]["sha256"] == load_repository_catalog(ROOT).sha256


def test_v3_does_not_require_profile_or_decoder_duplication(tmp_path: Path) -> None:
    _write_ctc_candidate_v3(tmp_path)
    raw = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert "decoder" not in raw
    assert "artifact_contract" not in raw
    assert "features" not in raw
    assert "profile" not in raw["variants"]["ctc"]
    candidate = CandidateArtifacts.load(tmp_path, repository_root=ROOT)
    assert candidate.decoder == "ctc"


def test_rejects_catalog_pin_mismatch(tmp_path: Path) -> None:
    _write_ctc_candidate_v3(tmp_path)
    path = tmp_path / "metadata.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["catalog"]["sha256"] = "0" * 64
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(CandidateMetadataError, match="catalog SHA-256"):
        CandidateArtifacts.load(tmp_path, repository_root=ROOT, verify_artifacts=False)


def test_rejects_artifact_path_escape(tmp_path: Path) -> None:
    _write_ctc_candidate_v3(tmp_path)
    path = tmp_path / "metadata.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["variants"]["ctc"]["artifacts"]["primary"]["path"] = "../model.onnx"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(CandidateMetadataError, match="escapes candidate root"):
        CandidateArtifacts.load(tmp_path, repository_root=ROOT, verify_artifacts=False)


def test_schema_v2_remains_readable_for_existing_candidates(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"v2")
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {
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
                    "io": {"primary": {"input": "audio", "logits_output": "logits"}},
                    "decoder_config": {"blank_id": 0},
                },
                "tokenizer": None,
                "features": {},
            }
        ),
        encoding="utf-8",
    )
    candidate = CandidateArtifacts.load(tmp_path)
    assert candidate.schema_version == 2
    assert candidate.decoder == "ctc"


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
