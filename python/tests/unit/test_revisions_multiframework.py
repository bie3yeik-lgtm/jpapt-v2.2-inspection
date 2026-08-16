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


def _resolved(parent: Path) -> None:
    _write(
        parent,
        "resolved.json",
        {"schema_version": 1, "config_version": "config-000001"},
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
                "sha256": SHA,
                "manifest": "evaluation/manifests/smoke.json",
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
        "upstream": {"repo_id": "example/upstream-asr", "revision": "upstream-sha"},
        "tokenizer": {"repo_id": "example/tokenizer", "revision": "tokenizer-sha"},
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


def _bundle_root(tmp_path: Path) -> Path:
    root = tmp_path / "revisions"
    _resolved(tmp_path)
    return root


def _write_bundle(
    root: Path,
    *,
    framework: str = "transformers",
    profile_set: str = "whisper-autoregressive-v1",
) -> None:
    _write(root, "reference.json", _reference(framework=framework))
    _write(root, "evaluation-schema.json", _evaluation_schema())
    _write(root, "datasets-lock.json", _datasets_lock())
    _write(root, "runtime.json", _runtime(profile_set))


def test_revision_bundle_materializes_strict_snapshot(tmp_path: Path) -> None:
    root = _bundle_root(tmp_path)
    _write_bundle(root)
    bundle = load_revision_bundle(root)
    snapshot = bundle.snapshot()
    assert snapshot.config_version == "config-000001"
    assert snapshot.reference.upstream.revision == "upstream-sha"
    assert snapshot.datasets.entries[0].subset == "default"
    assert snapshot.datasets.entries[0].sha256 == SHA
    assert snapshot.runtime.profile_set == "whisper-autoregressive-v1"


def test_unknown_fields_are_rejected(tmp_path: Path) -> None:
    root = _bundle_root(tmp_path)
    value = _reference()
    value["legacy_decoder"] = "ctc"
    _write(root, "reference.json", value)
    _write(root, "evaluation-schema.json", _evaluation_schema())
    _write(root, "datasets-lock.json", _datasets_lock())
    _write(root, "runtime.json", _runtime("whisper-autoregressive-v1"))
    with pytest.raises(RevisionError, match="unsupported fields"):
        load_revision_bundle(root)


def test_missing_runtime_is_rejected(tmp_path: Path) -> None:
    root = _bundle_root(tmp_path)
    _write(root, "reference.json", _reference())
    _write(root, "evaluation-schema.json", _evaluation_schema())
    _write(root, "datasets-lock.json", _datasets_lock())
    with pytest.raises(RevisionError, match="runtime.json is required"):
        load_revision_bundle(root)


def test_missing_config_version_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "revisions"
    _write_bundle(root)
    with pytest.raises(RevisionError, match="resolved.json is required"):
        load_revision_bundle(root)


def test_dataset_execution_sha_is_required(tmp_path: Path) -> None:
    root = _bundle_root(tmp_path)
    datasets = _datasets_lock()
    datasets["datasets"][0].pop("sha256")  # type: ignore[index,union-attr]
    _write(root, "reference.json", _reference())
    _write(root, "evaluation-schema.json", _evaluation_schema())
    _write(root, "datasets-lock.json", datasets)
    _write(root, "runtime.json", _runtime("whisper-autoregressive-v1"))
    bundle = load_revision_bundle(root)
    with pytest.raises(RevisionError, match="requires sha256 before execution"):
        bundle.snapshot()


def test_nulls_are_rejected_at_revision_boundary(tmp_path: Path) -> None:
    root = _bundle_root(tmp_path)
    reference = _reference()
    reference["reference"]["canonical_framework"] = None  # type: ignore[index]
    _write(root, "reference.json", reference)
    _write(root, "evaluation-schema.json", _evaluation_schema())
    _write(root, "datasets-lock.json", _datasets_lock())
    _write(root, "runtime.json", _runtime("whisper-autoregressive-v1"))
    with pytest.raises(RevisionError, match="null values are not allowed"):
        load_revision_bundle(root)


def test_runtime_catalog_pin_mismatch_is_rejected(tmp_path: Path) -> None:
    root = _bundle_root(tmp_path)
    _write(root, "reference.json", _reference())
    _write(root, "evaluation-schema.json", _evaluation_schema())
    _write(root, "datasets-lock.json", _datasets_lock())
    runtime = _runtime("whisper-autoregressive-v1")
    runtime["catalog"]["sha256"] = "0" * 64  # type: ignore[index]
    _write(root, "runtime.json", runtime)
    with pytest.raises(RevisionError, match="catalog SHA-256"):
        load_revision_bundle(root)
