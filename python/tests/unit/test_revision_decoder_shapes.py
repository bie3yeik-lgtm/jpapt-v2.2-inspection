from __future__ import annotations

import json
from pathlib import Path

import pytest

from parakeet_onnx.hf.revisions import RevisionError, load_revision_bundle


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


def _reference(decoders: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "development_artifact": {
            "repo_id": "gawohok7/jpapt-v2.2-dev",
            "revision": "artifact-sha",
        },
        "upstream": {
            "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
            "revision": "upstream-sha",
        },
        "tokenizer": {
            "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
            "revision": "tokenizer-sha",
        },
        "reference": {
            "id": "nemo-reference-v1",
            "revision": "reference-sha",
            "canonical_framework": "nemo",
        },
        "decoders": decoders,
    }


def _evaluation(decoders: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "schema": {"id": "asr-eval", "revision": "schema-sha"},
        "decoders": decoders,
    }


def test_structured_decoder_entries_are_normalized(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "reference.json",
        _reference(
            {
                "supported": [
                    {"id": "ctc", "enabled": True},
                    {"name": "tdt", "enabled": True},
                ],
                "default": {"id": "ctc"},
            }
        ),
    )
    _write(
        tmp_path,
        "evaluation-schema.json",
        _evaluation(
            {
                "supported": [
                    {"id": "ctc", "thresholds": {}},
                    {"type": "tdt", "thresholds": {}},
                ],
                "default": {"decoder": "ctc"},
            }
        ),
    )
    _write(tmp_path, "datasets-lock.json", _datasets())

    bundle = load_revision_bundle(tmp_path)

    assert bundle.reference.decoders.supported == ("ctc", "tdt")
    assert bundle.reference.decoders.default == "ctc"
    assert bundle.evaluation_schema.decoders.supported == ("ctc", "tdt")


def test_decorders_typo_is_rejected(tmp_path: Path) -> None:
    value = _reference(
        {
            "supported": ["whisper_autoregressive"],
            "default": "whisper_autoregressive",
        }
    )
    value["decorders"] = value.pop("decoders")
    _write(tmp_path, "reference.json", value)
    _write(
        tmp_path,
        "evaluation-schema.json",
        _evaluation(
            {
                "supported": ["whisper_autoregressive"],
                "default": "whisper_autoregressive",
            }
        ),
    )
    _write(tmp_path, "datasets-lock.json", _datasets())

    with pytest.raises(RevisionError, match="'decoders' must be an object"):
        load_revision_bundle(tmp_path)


def test_single_decoder_field_is_rejected(tmp_path: Path) -> None:
    value = _reference({"supported": ["ctc"], "default": "ctc"})
    value.pop("decoders")
    value["decoder"] = "ctc"
    _write(tmp_path, "reference.json", value)
    _write(
        tmp_path,
        "evaluation-schema.json",
        _evaluation({"supported": ["ctc"], "default": "ctc"}),
    )
    _write(tmp_path, "datasets-lock.json", _datasets())

    with pytest.raises(RevisionError, match="'decoders' must be an object"):
        load_revision_bundle(tmp_path)
