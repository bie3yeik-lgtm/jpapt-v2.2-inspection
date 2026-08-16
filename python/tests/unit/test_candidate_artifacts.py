from __future__ import annotations

import json
from pathlib import Path

import onnx
from onnx import TensorProto, helper
import pytest

from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.runtime.artifacts import CandidateArtifacts, CandidateMetadataError


ROOT = Path(__file__).resolve().parents[3]


def _write_ctc_model(path: Path) -> None:
    audio = helper.make_tensor_value_info("audio_signal", TensorProto.FLOAT, [1, "samples"])
    length = helper.make_tensor_value_info("length", TensorProto.INT64, [1])
    logits = helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, "frames", 3])
    graph = helper.make_graph([], "ctc", [audio, length], [logits])
    model = helper.make_model(graph)
    onnx.save(model, path)


def _write_minimal_candidate(root: Path) -> None:
    _write_ctc_model(root / "model.onnx")
    (root / "vocabulary.json").write_text(
        json.dumps(["a", "b", "<blank>"]) + "\n", encoding="utf-8"
    )
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "profile_set": "parakeet-tdt-ctc-v1",
                "variants": {
                    "ctc": {
                        "artifacts": {"primary": "model.onnx"},
                        "tokenizer": "vocabulary.json",
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_minimal_candidate_derives_all_runtime_provenance(tmp_path: Path) -> None:
    _write_minimal_candidate(tmp_path)
    (tmp_path / ".candidate-id").write_text("parakeet-candidate-000002\n", encoding="utf-8")

    candidate = CandidateArtifacts.load(tmp_path, repository_root=ROOT)

    assert candidate.candidate_id == "parakeet-candidate-000002"
    assert candidate.profile_set_id == "parakeet-tdt-ctc-v1"
    assert candidate.variant == "ctc"
    assert candidate.profile_id == "ctc-v1"
    assert candidate.decoder == "ctc"
    assert candidate.artifact_contract == "ctc-single-graph-v1"
    assert candidate.runtime_contract["io"]["primary"]["input"] == "audio_signal"
    assert candidate.runtime_contract["io"]["primary"]["length_input"] == "length"
    assert candidate.runtime_contract["io"]["primary"]["logits_output"] == "logits"
    assert candidate.runtime_contract["decoder_config"]["blank_id"] == 2
    assert candidate.tokenizer is not None
    assert candidate.tokenizer.kind == "vocabulary"
    assert len(candidate.artifact("primary").sha256) == 64
    assert candidate.artifact("primary").size_bytes > 0
    assert len(candidate.bundle_sha256) == 64
    provenance = candidate.provenance_dict()
    assert provenance["catalog"]["sha256"] == load_repository_catalog(ROOT).sha256
    assert provenance["artifacts"]["primary"]["sha256"] == candidate.artifact("primary").sha256


def test_conventional_vocabulary_path_can_be_omitted(tmp_path: Path) -> None:
    _write_minimal_candidate(tmp_path)
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    metadata["variants"]["ctc"].pop("tokenizer")
    (tmp_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    candidate = CandidateArtifacts.load(tmp_path, repository_root=ROOT)
    assert candidate.tokenizer is not None
    assert candidate.tokenizer.path == tmp_path / "vocabulary.json"


def test_verbose_generated_fields_are_rejected_from_human_metadata(tmp_path: Path) -> None:
    _write_minimal_candidate(tmp_path)
    path = tmp_path / "metadata.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["candidate_id"] = "must-not-be-authored"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(CandidateMetadataError, match="schema violation"):
        CandidateArtifacts.load(tmp_path, repository_root=ROOT)


def test_artifact_path_escape_is_rejected(tmp_path: Path) -> None:
    _write_minimal_candidate(tmp_path)
    path = tmp_path / "metadata.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["variants"]["ctc"]["artifacts"]["primary"] = "../model.onnx"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(CandidateMetadataError, match="escapes candidate root"):
        CandidateArtifacts.load(tmp_path, repository_root=ROOT)


def test_legacy_candidate_shapes_are_not_accepted(tmp_path: Path) -> None:
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "candidate_id": "legacy",
                "decoder": "ctc",
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CandidateMetadataError, match="schema violation"):
        CandidateArtifacts.load(tmp_path, repository_root=ROOT)
