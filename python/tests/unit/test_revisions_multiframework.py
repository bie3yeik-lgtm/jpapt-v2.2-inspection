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
            "default": decoders[0] if decoders else None,
        },
    }


def test_transformers_revision_bundle_uses_explicit_identities(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "reference.json",
        {
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
                "id": "transformers-reference-v1",
                "revision": "reference-sha",
                "canonical_framework": "transformers",
            },
            "decoders": {
                "supported": ["whisper_autoregressive"],
                "default": "whisper_autoregressive",
            },
        },
    )
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
    assert reference.canonical_framework == "transformers"
    assert reference.decoders.default == "whisper_autoregressive"
    assert reference.legacy_model_shape is False
    # Compatibility aliases still identify the development artifact.
    assert reference.model_id == "gawohok7/tf-v1-onnx-dev"
    assert reference.model_revision == "artifact-sha"


def test_nemo_legacy_revision_bundle_remains_compatible(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "reference.json",
        {
            "schema_version": 1,
            "model": {
                "repo_id": "gawohok7/jpapt-v2.2-dev",
                "revision": "artifact-sha",
                "tokenizer_revision": "legacy-tokenizer-sha",
            },
            "reference": {
                "id": "nemo-reference-v1",
                "revision": "reference-sha",
                "canonical_framework": "nemo",
            },
            "decoders": {
                "supported": ["ctc", "tdt"],
                "default": "ctc",
            },
        },
    )
    _write(
        tmp_path,
        "evaluation-schema.json",
        _evaluation_schema("ctc", "tdt"),
    )
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    bundle = load_revision_bundle(tmp_path)
    reference = bundle.reference

    assert reference.development_artifact_repo_id == "gawohok7/jpapt-v2.2-dev"
    assert reference.development_artifact_revision == "artifact-sha"
    assert reference.upstream_repo_id is None
    assert reference.tokenizer_repo_id is None
    assert reference.tokenizer_revision == "legacy-tokenizer-sha"
    assert reference.legacy_model_shape is True
    assert reference.canonical_framework == "nemo"
    assert reference.decoders.supported == ("ctc", "tdt")


def test_decoder_mismatch_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "reference.json",
        {
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
            "reference": {"canonical_framework": "transformers"},
            "decoders": {
                "supported": ["whisper_autoregressive"],
                "default": "whisper_autoregressive",
            },
        },
    )
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema("ctc", "tdt"))
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    with pytest.raises(
        RevisionError,
        match="does not support all reference decoders",
    ):
        load_revision_bundle(tmp_path)


def test_legacy_revision_documents_without_framework_still_load(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "reference.json",
        {
            "schema_version": 1,
            "model": {
                "repo_id": "gawohok7/jpapt-v2.2-dev",
                "revision": "model-sha",
            },
            "reference": {
                "id": "legacy-reference",
                "revision": "reference-sha",
            },
        },
    )
    _write(
        tmp_path,
        "evaluation-schema.json",
        {
            "schema_version": 1,
            "schema": {"id": "legacy-schema", "revision": "schema-sha"},
        },
    )
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    bundle = load_revision_bundle(tmp_path)
    assert bundle.reference.canonical_framework is None
    assert bundle.reference.decoders.supported == ()
    assert bundle.reference.legacy_model_shape is True


def test_new_shape_requires_revision_for_each_identity(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "reference.json",
        {
            "schema_version": 1,
            "development_artifact": {
                "repo_id": "gawohok7/tf-v1-onnx-dev",
                "revision": "artifact-sha",
            },
            "upstream": {
                "repo_id": "kotoba-tech/kotoba-whisper-v1.0"
            },
        },
    )
    _write(tmp_path, "evaluation-schema.json", _evaluation_schema("ctc"))
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    with pytest.raises(RevisionError, match="'revision' must be a non-empty string"):
        load_revision_bundle(tmp_path)
