from __future__ import annotations

import json
from pathlib import Path

import pytest

from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.hf.revisions import RevisionError, load_revision_bundle
from parakeet_onnx.hf.snapshot import normalized_revision_snapshot


ROOT = Path(__file__).resolve().parents[3]


def _write(root: Path, name: str, value: dict[str, object]) -> None:
    (root / name).write_text(json.dumps(value), encoding="utf-8")


def _datasets_lock() -> dict[str, object]:
    return {
        "schema_version": 1,
        "datasets": [
            {
                "id": "jsut-basic5000",
                "repo_id": "japanese-asr/ja_asr.jsut_basic5000",
                "revision": "dataset-sha",
                "split": "test",
            }
        ],
    }


def _evaluation_schema() -> dict[str, object]:
    return {
        "schema_version": 1,
        "schema": {"id": "asr-evaluation-v1", "revision": "schema-sha"},
    }


def _reference(*, framework: str = "transformers") -> dict[str, object]:
    return {
        "schema_version": 1,
        "development_artifact": {
            "repo_id": "example/dev-artifact",
            "revision": "artifact-sha",
        },
        "upstream": {
            "repo_id": "example/upstream-asr",
            "revision": "upstream-sha",
        },
        "tokenizer": {
            "repo_id": "example/tokenizer",
            "revision": "tokenizer-sha",
        },
        "reference": {
            "id": "canonical-reference-v1",
            "revision": "reference-sha",
            "canonical_framework": framework,
        },
    }


def _runtime(profile_set: str) -> dict[str, object]:
    catalog = load_repository_catalog(ROOT)
    return {
        "schema_version": 1,
        "catalog": {"id": catalog.catalog_id, "sha256": catalog.sha256},
        "profile_set": profile_set,
    }


def _write_normalized_bundle(
    root: Path,
    *,
    framework: str = "transformers",
    profile_set: str = "whisper-autoregressive-v1",
) -> None:
    _write(root, "reference.json", _reference(framework=framework))
    _write(root, "evaluation-schema.json", _evaluation_schema())
    _write(root, "datasets-lock.json", _datasets_lock())
    _write(root, "runtime.json", _runtime(profile_set))


def test_transformers_revision_bundle_uses_explicit_identities(tmp_path: Path) -> None:
    _write_normalized_bundle(tmp_path)
    bundle = load_revision_bundle(tmp_path)
    reference = bundle.reference

    assert reference.development_artifact_repo_id == "example/dev-artifact"
    assert reference.development_artifact_revision == "artifact-sha"
    assert reference.upstream_repo_id == "example/upstream-asr"
    assert reference.upstream_revision == "upstream-sha"
    assert reference.tokenizer_repo_id == "example/tokenizer"
    assert reference.tokenizer_revision == "tokenizer-sha"
    assert reference.reference_id == "canonical-reference-v1"
    assert reference.reference_revision == "reference-sha"
    assert reference.canonical_framework == "transformers"
    assert bundle.runtime is not None
    assert bundle.runtime.profile_set_id == "whisper-autoregressive-v1"
    assert reference.decoders.default == "whisper_autoregressive"


def test_normalized_snapshot_does_not_repeat_decoder_declarations(tmp_path: Path) -> None:
    _write_normalized_bundle(
        tmp_path,
        framework="nemo",
        profile_set="parakeet-tdt-ctc-v1",
    )
    value = normalized_revision_snapshot(load_revision_bundle(tmp_path))
    assert set(value["runtime"]) == {"document_sha256", "catalog", "profile_set"}
    assert "decoders" not in value["reference"]
    assert "decoders" not in value["evaluation_schema"]


def test_normalized_config_rejects_duplicate_decoder_fields(tmp_path: Path) -> None:
    reference = _reference(framework="nemo")
    reference["decoders"] = {"supported": ["ctc", "tdt"], "default": "ctc"}
    _write(tmp_path, "reference.json", reference)
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema())
    _write(tmp_path, "datasets-lock.json", _datasets_lock())
    _write(tmp_path, "runtime.json", _runtime("parakeet-tdt-ctc-v1"))

    with pytest.raises(RevisionError, match="must not repeat decoder declarations"):
        load_revision_bundle(tmp_path)


def test_legacy_model_identity_is_rejected(tmp_path: Path) -> None:
    value = _reference(framework="nemo")
    value.pop("development_artifact")
    value["model"] = {
        "repo_id": "example/old-model",
        "revision": "artifact-sha",
    }
    _write(tmp_path, "reference.json", value)
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema())
    _write(tmp_path, "datasets-lock.json", _datasets_lock())
    _write(tmp_path, "runtime.json", _runtime("parakeet-tdt-ctc-v1"))

    with pytest.raises(RevisionError, match="unsupported legacy fields"):
        load_revision_bundle(tmp_path)


def test_mixed_legacy_and_new_identity_is_rejected(tmp_path: Path) -> None:
    value = _reference()
    value["model"] = {
        "repo_id": "example/old-model",
        "revision": "old-sha",
    }
    _write(tmp_path, "reference.json", value)
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema())
    _write(tmp_path, "datasets-lock.json", _datasets_lock())
    _write(tmp_path, "runtime.json", _runtime("whisper-autoregressive-v1"))

    with pytest.raises(RevisionError, match="unsupported legacy fields"):
        load_revision_bundle(tmp_path)


def test_missing_upstream_identity_is_rejected(tmp_path: Path) -> None:
    value = _reference()
    value.pop("upstream")
    _write(tmp_path, "reference.json", value)
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema())
    _write(tmp_path, "datasets-lock.json", _datasets_lock())
    _write(tmp_path, "runtime.json", _runtime("whisper-autoregressive-v1"))

    with pytest.raises(RevisionError, match="'upstream' must be an object"):
        load_revision_bundle(tmp_path)


def test_missing_tokenizer_identity_is_rejected(tmp_path: Path) -> None:
    value = _reference()
    value.pop("tokenizer")
    _write(tmp_path, "reference.json", value)
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema())
    _write(tmp_path, "datasets-lock.json", _datasets_lock())
    _write(tmp_path, "runtime.json", _runtime("whisper-autoregressive-v1"))

    with pytest.raises(RevisionError, match="'tokenizer' must be an object"):
        load_revision_bundle(tmp_path)


def test_runtime_catalog_pin_mismatch_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "reference.json", _reference())
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema())
    _write(tmp_path, "datasets-lock.json", _datasets_lock())
    runtime = _runtime("whisper-autoregressive-v1")
    runtime["catalog"]["sha256"] = "0" * 64  # type: ignore[index]
    _write(tmp_path, "runtime.json", runtime)

    with pytest.raises(RevisionError, match="catalog SHA-256"):
        load_revision_bundle(tmp_path)


def test_each_identity_requires_revision(tmp_path: Path) -> None:
    value = _reference()
    value["upstream"] = {"repo_id": "example/upstream-asr"}
    _write(tmp_path, "reference.json", value)
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema())
    _write(tmp_path, "datasets-lock.json", _datasets_lock())
    _write(tmp_path, "runtime.json", _runtime("whisper-autoregressive-v1"))

    with pytest.raises(RevisionError, match="'revision' must be a non-empty string"):
        load_revision_bundle(tmp_path)
