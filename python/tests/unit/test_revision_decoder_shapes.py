from __future__ import annotations

import json
from pathlib import Path

from parakeet_onnx.hf.revisions import load_revision_bundle


def _write(root: Path, name: str, value: dict[str, object]) -> None:
    (root / name).write_text(json.dumps(value), encoding="utf-8")


def _datasets() -> dict[str, object]:
    return {
        "schema_version": 1,
        "datasets": [
            {
                "id": "jsut-basic5000",
                "repo_id": "japanese-asr/ja_asr.jsut_basic5000",
                "revision": "dataset-sha",
            }
        ],
    }


def test_structured_decoder_entries_are_normalized(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "reference.json",
        {
            "schema_version": 1,
            "model": {
                "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
                "revision": "model-sha",
            },
            "reference": {"canonical_framework": "nemo"},
            "decoders": {
                "supported": [
                    {"id": "ctc", "enabled": True},
                    {"name": "tdt", "enabled": True},
                ],
                "default": {"id": "ctc"},
            },
        },
    )
    _write(
        tmp_path,
        "evaluation-schema.json",
        {
            "schema_version": 1,
            "schema": {"id": "asr-eval", "revision": "schema-sha"},
            "decoders": {
                "supported": [
                    {"id": "ctc", "thresholds": {}},
                    {"type": "tdt", "thresholds": {}},
                ],
                "default": {"decoder": "ctc"},
            },
        },
    )
    _write(tmp_path, "datasets-lock.json", _datasets())

    bundle = load_revision_bundle(tmp_path)

    assert bundle.reference.decoders.supported == ("ctc", "tdt")
    assert bundle.reference.decoders.default == "ctc"
    assert bundle.evaluation_schema.decoders.supported == ("ctc", "tdt")


def test_decorders_typo_is_accepted_for_legacy_bucket(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "reference.json",
        {
            "schema_version": 1,
            "model": {
                "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
                "revision": "model-sha",
            },
            "reference": {"canonical_framework": "transformers"},
            "decorders": {
                "supported": [{"id": "whisper_autoregressive"}],
                "default": "whisper_autoregressive",
            },
        },
    )
    _write(
        tmp_path,
        "evaluation-schema.json",
        {
            "schema_version": 1,
            "schema": {"id": "asr-eval", "revision": "schema-sha"},
            "decoders": {
                "supported": ["whisper_autoregressive"],
                "default": "whisper_autoregressive",
            },
        },
    )
    _write(tmp_path, "datasets-lock.json", _datasets())

    bundle = load_revision_bundle(tmp_path)
    assert bundle.reference.decoders.default == "whisper_autoregressive"
