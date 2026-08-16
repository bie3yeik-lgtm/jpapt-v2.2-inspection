from __future__ import annotations

import json
from pathlib import Path

import onnx
from onnx import TensorProto, helper

from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.hf.revisions import load_revision_bundle
from parakeet_onnx.runtime.artifacts import CandidateArtifacts


ROOT = Path(__file__).resolve().parents[3]


def _save(path: Path, inputs: list[object], outputs: list[object]) -> None:
    onnx.save(helper.make_model(helper.make_graph([], path.stem, inputs, outputs)), path)


def _write_ctc(path: Path) -> None:
    _save(
        path,
        [
            helper.make_tensor_value_info("audio_signal", TensorProto.FLOAT, [1, "samples"]),
            helper.make_tensor_value_info("length", TensorProto.INT64, [1]),
        ],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, "frames", 3])],
    )


def _write_tdt(root: Path) -> None:
    (root / "model_config.json").write_text(
        json.dumps({"tdt_durations": [0, 1, 2]}) + "\n",
        encoding="utf-8",
    )
    _save(
        root / "encoder.onnx",
        [
            helper.make_tensor_value_info("audio_signal", TensorProto.FLOAT, [1, "samples"]),
            helper.make_tensor_value_info("audio_length", TensorProto.INT64, [1]),
        ],
        [
            helper.make_tensor_value_info("encoded", TensorProto.FLOAT, [1, "frames", 64]),
            helper.make_tensor_value_info("encoded_length", TensorProto.INT64, [1]),
        ],
    )
    _save(
        root / "predictor.onnx",
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
        root / "joint.onnx",
        [
            helper.make_tensor_value_info("encoder_frame", TensorProto.FLOAT, [1, 1, 64]),
            helper.make_tensor_value_info("prediction", TensorProto.FLOAT, [1, 1, 64]),
        ],
        [
            helper.make_tensor_value_info("token_logits", TensorProto.FLOAT, [1, 1, 3]),
            helper.make_tensor_value_info("duration_logits", TensorProto.FLOAT, [1, 1, 3]),
        ],
    )


def test_runtime_catalog_centralizes_parakeet_variants() -> None:
    catalog = load_repository_catalog(ROOT)
    profile_set = catalog.profile_set("parakeet-tdt-ctc-v1")
    assert profile_set.profile_id_for("ctc") == "ctc-v1"
    assert profile_set.profile_id_for("tdt") == "tdt-v1"
    assert catalog.decoder_profile("ctc-v1").decoder == "ctc"
    assert catalog.decoder_profile("tdt-v1").decoder == "tdt"


def test_one_minimal_candidate_metadata_selects_ctc_or_tdt_without_rewrite(
    tmp_path: Path,
) -> None:
    _write_ctc(tmp_path / "model.onnx")
    _write_tdt(tmp_path)
    (tmp_path / "vocabulary.json").write_text(
        json.dumps(["<blank>", "<bos>", "a"]) + "\n", encoding="utf-8"
    )
    metadata = {
        "profile_set": "parakeet-tdt-ctc-v1",
        "variants": {
            "ctc": {
                "artifacts": {"primary": "model.onnx"},
                "tokenizer": "vocabulary.json",
            },
            "tdt": {
                "artifacts": {
                    "encoder": "encoder.onnx",
                    "predictor": "predictor.onnx",
                    "joint": "joint.onnx",
                },
                "tokenizer": "vocabulary.json",
            },
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    before = metadata_path.read_bytes()

    ctc = CandidateArtifacts.load(tmp_path, variant="ctc", repository_root=ROOT)
    tdt = CandidateArtifacts.load(tmp_path, variant="tdt", repository_root=ROOT)
    default = CandidateArtifacts.load(tmp_path, repository_root=ROOT)

    assert metadata_path.read_bytes() == before
    assert ctc.decoder == "ctc"
    assert ctc.profile_id == "ctc-v1"
    assert ctc.artifact_contract == "ctc-single-graph-v1"
    assert ctc.runtime_contract["decoder_config"]["blank_id"] == 0
    assert set(ctc.artifacts) == {"primary"}
    assert tdt.decoder == "tdt"
    assert tdt.profile_id == "tdt-v1"
    assert tdt.artifact_contract == "tdt-multi-graph-v1"
    assert tdt.runtime_contract["decoder_config"]["bos_id"] == 1
    assert tdt.runtime_contract["decoder_config"]["durations"] == [0, 1, 2]
    assert set(tdt.artifacts) == {"encoder", "predictor", "joint"}
    assert default.variant == "ctc"


def test_normalized_runtime_lock_resolves_variants_from_catalog(tmp_path: Path) -> None:
    catalog = load_repository_catalog(ROOT)
    revisions = tmp_path / "revisions"
    revisions.mkdir()
    (tmp_path / "resolved.json").write_text(
        json.dumps({"schema_version": 1, "config_version": "config-000001"}),
        encoding="utf-8",
    )
    (revisions / "reference.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "development_artifact": {"repo_id": "dev/model", "revision": "dev-sha"},
                "upstream": {"repo_id": "up/model", "revision": "up-sha"},
                "tokenizer": {"repo_id": "up/model", "revision": "tok-sha"},
                "reference": {
                    "id": "nemo-reference-v1",
                    "revision": "git-sha",
                    "canonical_framework": "nemo",
                },
            }
        ),
        encoding="utf-8",
    )
    (revisions / "evaluation-schema.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "schema": {"id": "eval-v1", "revision": "eval-sha"},
            }
        ),
        encoding="utf-8",
    )
    (revisions / "datasets-lock.json").write_text(
        json.dumps({"schema_version": 1, "datasets": []}), encoding="utf-8"
    )
    (revisions / "runtime.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "catalog": {"id": catalog.catalog_id, "sha256": catalog.sha256},
                "profile_set": "parakeet-tdt-ctc-v1",
            }
        ),
        encoding="utf-8",
    )

    bundle = load_revision_bundle(revisions)
    assert bundle.runtime.profile_set_id == "parakeet-tdt-ctc-v1"
    assert bundle.runtime.resolve_variant(None, catalog=catalog) == (
        "ctc",
        "ctc-v1",
        "ctc",
    )
    assert bundle.runtime.resolve_variant("tdt", catalog=catalog) == (
        "tdt",
        "tdt-v1",
        "tdt",
    )
    snapshot = bundle.to_dict()
    assert snapshot["config_version"] == "config-000001"
    assert set(snapshot["runtime"]) == {"document_sha256", "catalog", "profile_set"}
    assert "decoders" not in snapshot["reference"]
    assert "decoders" not in snapshot["evaluation_schema"]
