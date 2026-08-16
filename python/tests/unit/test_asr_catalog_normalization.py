from __future__ import annotations

import hashlib
import json
from pathlib import Path

from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.hf.revisions import load_revision_bundle
from parakeet_onnx.runtime.artifacts import CandidateArtifacts


ROOT = Path(__file__).resolve().parents[3]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": _sha(path),
        "size_bytes": path.stat().st_size,
    }


def test_catalog_centralizes_prefixes_and_parakeet_variants() -> None:
    catalog = load_repository_catalog(ROOT)
    profile_set = catalog.profile_set("parakeet-tdt-ctc-v1")
    assert profile_set.candidate_prefix_key == "candidate.parakeet"
    assert catalog.prefix(profile_set.candidate_prefix_key) == "parakeet-candidate"
    assert profile_set.profile_id_for("ctc") == "ctc-v1"
    assert profile_set.profile_id_for("tdt") == "tdt-v1"
    assert catalog.decoder_profile("ctc-v1").decoder == "ctc"
    assert catalog.decoder_profile("tdt-v1").decoder == "tdt"


def test_one_candidate_metadata_can_select_ctc_or_tdt_without_rewrite(
    tmp_path: Path,
) -> None:
    model = tmp_path / "model.onnx"
    encoder = tmp_path / "encoder.onnx"
    predictor = tmp_path / "predictor.onnx"
    joint = tmp_path / "joint.onnx"
    vocabulary = tmp_path / "vocabulary.json"
    for path, value in (
        (model, b"ctc"),
        (encoder, b"encoder"),
        (predictor, b"predictor"),
        (joint, b"joint"),
    ):
        path.write_bytes(value)
    vocabulary.write_text('["<blank>", "a"]\n', encoding="utf-8")

    metadata = {
        "schema_version": 3,
        "candidate_id": "parakeet-candidate-000002",
        "profile_set": "parakeet-tdt-ctc-v1",
        "variants": {
            "ctc": {
                "profile": "ctc-v1",
                "artifacts": {"primary": _artifact(model)},
                "bindings": {
                    "input_kind": "canonical_waveform",
                    "io": {
                        "primary": {
                            "input": "audio",
                            "length_input": "length",
                            "logits_output": "logits",
                        }
                    },
                    "decoder_config": {"blank_id": 0},
                },
                "tokenizer": {"path": "vocabulary.json"},
            },
            "tdt": {
                "profile": "tdt-v1",
                "artifacts": {
                    "encoder": _artifact(encoder),
                    "predictor": _artifact(predictor),
                    "joint": _artifact(joint),
                },
                "bindings": {
                    "input_kind": "canonical_waveform",
                    "io": {
                        "encoder": {"input": "audio", "output": "encoded"},
                        "predictor": {
                            "token_input": "token",
                            "output": "prediction",
                            "state_inputs": [],
                            "state_outputs": [],
                            "state_shapes": [],
                            "state_dtypes": [],
                        },
                        "joint": {
                            "encoder_input": "encoded_frame",
                            "predictor_input": "prediction",
                            "token_output": "token_logits",
                            "duration_output": "duration_logits",
                            "output_mode": "separate",
                        },
                    },
                    "decoder_config": {
                        "blank_id": 0,
                        "bos_id": 1,
                        "durations": [0, 1, 2],
                    },
                },
                "tokenizer": {"path": "vocabulary.json"},
            },
        },
    }
    (tmp_path / "metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    ctc = CandidateArtifacts.load(tmp_path, variant="ctc", repository_root=ROOT)
    tdt = CandidateArtifacts.load(tmp_path, variant="tdt", repository_root=ROOT)
    default = CandidateArtifacts.load(tmp_path, repository_root=ROOT)

    assert ctc.decoder == "ctc"
    assert ctc.profile_id == "ctc-v1"
    assert ctc.artifact_contract == "ctc-single-graph-v1"
    assert set(ctc.artifacts) == {"primary"}
    assert tdt.decoder == "tdt"
    assert tdt.profile_id == "tdt-v1"
    assert tdt.artifact_contract == "tdt-multi-graph-v1"
    assert set(tdt.artifacts) == {"encoder", "predictor", "joint"}
    assert default.variant == "ctc"


def test_normalized_runtime_lock_derives_decoder_set_from_catalog(
    tmp_path: Path,
) -> None:
    catalog = load_repository_catalog(ROOT)
    revisions = tmp_path / "revisions"
    revisions.mkdir()
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

    # Runtime loader discovers the repository catalog from cwd when the temp
    # revision directory is outside the checkout.
    bundle = load_revision_bundle(revisions)
    assert bundle.runtime is not None
    assert bundle.runtime.profile_set_id == "parakeet-tdt-ctc-v1"
    assert bundle.reference.decoders.supported == ("ctc", "tdt")
    assert bundle.reference.decoders.default == "ctc"
