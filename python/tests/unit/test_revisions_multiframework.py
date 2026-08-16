from __future__ import annotations

import json
from pathlib import Path

import pytest

from parakeet_onnx.hf.revisions import RevisionError, load_revision_bundle


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


def _evaluation_schema(*decoders: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "schema": {"id": "asr-evaluation-v1", "revision": "schema-sha"},
        "decoders": {
            "supported": list(decoders),
            "default": decoders[0],
        },
    }


def _reference(*, framework: str = "transformers") -> dict[str, object]:
    return {
        "schema_version": 1,
        "development_artifact": {
            "repo_id": "gawohok7/tf-v1-onnx-dev",
            "revision": "artifact-sha",
        },
        "upstream": {
            "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
            "revision": "upstream-sha",
        },
        "tokenizer": {
            "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
            "revision": "tokenizer-sha",
        },
        "reference": {
            "id": "canonical-reference-v1",
            "revision": "reference-sha",
            "canonical_framework": framework,
        },
        "decoders": {
            "supported": ["whisper_autoregressive"],
            "default": "whisper_autoregressive",
        },
    }


def test_transformers_revision_bundle_uses_explicit_identities(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "reference.json", _reference())
    _write(
        tmp_path,
        "evaluation-schema.json",
        _evaluation_schema("whisper_autoregressive", "ctc", "tdt"),
    )
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    bundle = load_revision_bundle(tmp_path)
    reference = bundle.reference

    assert reference.development_artifact_repo_id == "gawohok7/tf-v1-onnx-dev"
    assert reference.development_artifact_revision == "artifact-sha"
    assert reference.upstream_repo_id == "kotoba-tech/kotoba-whisper-v1.0"
    assert reference.upstream_revision == "upstream-sha"
    assert reference.tokenizer_repo_id == "kotoba-tech/kotoba-whisper-v1.0"
    assert reference.tokenizer_revision == "tokenizer-sha"
    assert reference.reference_id == "canonical-reference-v1"
    assert reference.reference_revision == "reference-sha"
    assert reference.canonical_framework == "transformers"
    assert reference.decoders.default == "whisper_autoregressive"


def test_legacy_model_identity_is_rejected(tmp_path: Path) -> None:
    value = _reference(framework="nemo")
    value.pop("development_artifact")
    value["model"] = {
        "repo_id": "gawohok7/jpapt-v2.2-dev",
        "revision": "artifact-sha",
    }
    _write(tmp_path, "reference.json", value)
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema("ctc"))
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    with pytest.raises(RevisionError, match="'development_artifact' must be an object"):
        load_revision_bundle(tmp_path)


def test_missing_upstream_identity_is_rejected(tmp_path: Path) -> None:
    value = _reference()
    value.pop("upstream")
    _write(tmp_path, "reference.json", value)
    _write(
        tmp_path,
        "evaluation-schema.json",
        _evaluation_schema("whisper_autoregressive"),
    )
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    with pytest.raises(RevisionError, match="'upstream' must be an object"):
        load_revision_bundle(tmp_path)


def test_missing_tokenizer_identity_is_rejected(tmp_path: Path) -> None:
    value = _reference()
    value.pop("tokenizer")
    _write(tmp_path, "reference.json", value)
    _write(
        tmp_path,
        "evaluation-schema.json",
        _evaluation_schema("whisper_autoregressive"),
    )
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    with pytest.raises(RevisionError, match="'tokenizer' must be an object"):
        load_revision_bundle(tmp_path)


def test_decoder_mismatch_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "reference.json", _reference())
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema("ctc", "tdt"))
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    with pytest.raises(
        RevisionError,
        match="does not support all reference decoders",
    ):
        load_revision_bundle(tmp_path)


def test_each_identity_requires_revision(tmp_path: Path) -> None:
    value = _reference()
    value["upstream"] = {
        "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
    }
    _write(tmp_path, "reference.json", value)
    _write(
        tmp_path,
        "evaluation-schema.json",
        _evaluation_schema("whisper_autoregressive"),
    )
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    with pytest.raises(RevisionError, match="'revision' must be a non-empty string"):
        load_revision_bundle(tmp_path)
