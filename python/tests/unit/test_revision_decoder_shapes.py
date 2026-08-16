from __future__ import annotations

import json
from pathlib import Path

import pytest

from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.hf.revisions import RevisionError, load_revision_bundle


ROOT = Path(__file__).resolve().parents[3]


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


def _reference() -> dict[str, object]:
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
    }


def _evaluation() -> dict[str, object]:
    return {
        "schema_version": 1,
        "schema": {"id": "asr-eval", "revision": "schema-sha"},
    }


def _runtime() -> dict[str, object]:
    catalog = load_repository_catalog(ROOT)
    return {
        "schema_version": 1,
        "catalog": {"id": catalog.catalog_id, "sha256": catalog.sha256},
        "profile_set": "parakeet-tdt-ctc-v1",
    }


def _write_normalized(root: Path) -> None:
    _write(root, "reference.json", _reference())
    _write(root, "evaluation-schema.json", _evaluation())
    _write(root, "datasets-lock.json", _datasets())
    _write(root, "runtime.json", _runtime())


def test_runtime_profile_set_derives_ctc_and_tdt(tmp_path: Path) -> None:
    _write_normalized(tmp_path)
    bundle = load_revision_bundle(tmp_path)
    assert bundle.runtime is not None
    assert bundle.runtime.decoders.supported == ("ctc", "tdt")
    assert bundle.runtime.decoders.default == "ctc"
    assert bundle.reference.decoders.supported == ("ctc", "tdt")
    assert bundle.evaluation_schema.decoders.supported == ("ctc", "tdt")


def test_duplicate_decoder_declaration_is_rejected_in_normalized_config(
    tmp_path: Path,
) -> None:
    value = _reference()
    value["decoders"] = {"supported": ["ctc", "tdt"], "default": "ctc"}
    _write(tmp_path, "reference.json", value)
    _write(tmp_path, "evaluation-schema.json", _evaluation())
    _write(tmp_path, "datasets-lock.json", _datasets())
    _write(tmp_path, "runtime.json", _runtime())

    with pytest.raises(RevisionError, match="must not repeat decoder declarations"):
        load_revision_bundle(tmp_path)


def test_legacy_three_file_config_remains_readable(tmp_path: Path) -> None:
    reference = _reference()
    reference["decoders"] = {"supported": ["ctc", "tdt"], "default": "ctc"}
    evaluation = _evaluation()
    evaluation["decoders"] = {"supported": ["ctc", "tdt"], "default": "ctc"}
    _write(tmp_path, "reference.json", reference)
    _write(tmp_path, "evaluation-schema.json", evaluation)
    _write(tmp_path, "datasets-lock.json", _datasets())

    bundle = load_revision_bundle(tmp_path)
    assert bundle.runtime is None
    assert bundle.reference.decoders.supported == ("ctc", "tdt")
