from __future__ import annotations

import json
from pathlib import Path

import pytest

from parakeet_onnx.hf.revisions import (
    RevisionError,
    load_revision_bundle,
)


def _write(
    root: Path,
    name: str,
    value: dict[str, object],
) -> None:
    (root / name).write_text(
        json.dumps(value),
        encoding="utf-8",
    )


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


def test_transformers_revision_bundle(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "reference.json",
        {
            "schema_version": 1,
            "model": {
                "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
                "revision": "model-sha",
                "tokenizer_revision": "model-sha",
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
        {
            "schema_version": 1,
            "schema": {
                "id": "asr-evaluation-v1",
                "revision": "schema-sha",
            },
            "decoders": {
                "supported": [
                    "ctc",
                    "tdt",
                    "whisper_autoregressive",
                ],
                "default": "whisper_autoregressive",
            },
        },
    )
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    bundle = load_revision_bundle(tmp_path)

    assert bundle.reference.canonical_framework == "transformers"
    assert bundle.reference.decoders.default == "whisper_autoregressive"
    assert (
        "whisper_autoregressive"
        in bundle.evaluation_schema.decoders.supported
    )
    assert bundle.datasets.datasets[0].id == "jsut-basic5000"


def test_nemo_revision_bundle_remains_compatible(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "reference.json",
        {
            "schema_version": 1,
            "model": {
                "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
                "revision": "model-sha",
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
        {
            "schema_version": 1,
            "schema": {
                "id": "asr-evaluation-v1",
                "revision": "schema-sha",
            },
            "decoders": {
                "supported": ["ctc", "tdt"],
                "default": "ctc",
            },
        },
    )
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    bundle = load_revision_bundle(tmp_path)

    assert bundle.reference.canonical_framework == "nemo"
    assert bundle.reference.decoders.supported == ("ctc", "tdt")


def test_decoder_mismatch_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "reference.json",
        {
            "schema_version": 1,
            "model": {
                "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
                "revision": "model-sha",
            },
            "reference": {
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
        {
            "schema_version": 1,
            "schema": {
                "id": "asr-evaluation-v1",
                "revision": "schema-sha",
            },
            "decoders": {
                "supported": ["ctc", "tdt"],
                "default": "ctc",
            },
        },
    )
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
                "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
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
            "schema": {
                "id": "legacy-schema",
                "revision": "schema-sha",
            },
        },
    )
    _write(tmp_path, "datasets-lock.json", _datasets_lock())

    bundle = load_revision_bundle(tmp_path)
    assert bundle.reference.canonical_framework is None
    assert bundle.reference.decoders.supported == ()
