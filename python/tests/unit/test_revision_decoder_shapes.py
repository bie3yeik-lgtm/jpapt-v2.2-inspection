from __future__ import annotations

import json
from pathlib import Path

import pytest

from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.hf.revisions import RevisionError, load_revision_bundle


ROOT = Path(__file__).resolve().parents[3]
SHA = "1" * 64


def _write(root: Path, name: str, value: dict[str, object]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps(value), encoding="utf-8")


def _datasets() -> dict[str, object]:
    return {
        "schema_version": 1,
        "datasets": [
            {
                "id": "jsut-basic5000",
                "repo_id": "japanese-asr/ja_asr.jsut_basic5000",
                "revision": "dataset-sha",
                "sha256": SHA,
                "manifest": "evaluation/manifests/smoke.json",
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


def _revision_root(tmp_path: Path) -> Path:
    root = tmp_path / "revisions"
    _write(
        tmp_path,
        "resolved.json",
        {"schema_version": 1, "config_version": "config-000001"},
    )
    return root


def _write_normalized(tmp_path: Path) -> Path:
    root = _revision_root(tmp_path)
    _write(root, "reference.json", _reference())
    _write(root, "evaluation-schema.json", _evaluation())
    _write(root, "datasets-lock.json", _datasets())
    _write(root, "runtime.json", _runtime())
    return root


def test_runtime_profile_set_resolves_ctc_and_tdt_from_catalog(tmp_path: Path) -> None:
    root = _write_normalized(tmp_path)
    bundle = load_revision_bundle(root)
    catalog = load_repository_catalog(ROOT)

    assert bundle.runtime.profile_set_id == "parakeet-tdt-ctc-v1"
    assert bundle.runtime.resolve_variant(None, catalog=catalog) == ("ctc", "ctc-v1", "ctc")
    assert bundle.runtime.resolve_variant("tdt", catalog=catalog) == ("tdt", "tdt-v1", "tdt")
    snapshot = bundle.to_dict()
    assert snapshot["config_version"] == "config-000001"
    assert set(snapshot["runtime"]) == {"document_sha256", "catalog", "profile_set"}
    assert "decoders" not in snapshot["reference"]
    assert "decoders" not in snapshot["evaluation_schema"]


def test_duplicate_decoder_declaration_is_rejected(tmp_path: Path) -> None:
    root = _revision_root(tmp_path)
    value = _reference()
    value["decoders"] = {"supported": ["ctc", "tdt"], "default": "ctc"}
    _write(root, "reference.json", value)
    _write(root, "evaluation-schema.json", _evaluation())
    _write(root, "datasets-lock.json", _datasets())
    _write(root, "runtime.json", _runtime())

    with pytest.raises(RevisionError, match="unsupported fields"):
        load_revision_bundle(root)


def test_three_file_config_is_rejected(tmp_path: Path) -> None:
    root = _revision_root(tmp_path)
    _write(root, "reference.json", _reference())
    _write(root, "evaluation-schema.json", _evaluation())
    _write(root, "datasets-lock.json", _datasets())

    with pytest.raises(RevisionError, match="runtime.json is required"):
        load_revision_bundle(root)
