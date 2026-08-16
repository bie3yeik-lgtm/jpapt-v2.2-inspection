from __future__ import annotations

import json
from pathlib import Path

import pytest

from parakeet_onnx.datasets.errors import DatasetManifestError
from parakeet_onnx.datasets.manifest import ManifestLoader, stable_hash, stable_hash_bytes


MANIFEST_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["dataset_id", "count", "seed"],
    "properties": {
        "dataset_id": {"type": "string", "minLength": 1},
        "count": {"type": "integer", "minimum": 1},
        "seed": {"type": "string", "minLength": 1},
        "min_duration_sec": {"type": "number", "minimum": 0},
        "max_duration_sec": {"type": "number", "exclusiveMinimum": 0},
    },
}


def _write_schema(root: Path) -> None:
    path = root / "evaluation" / "schemas" / "manifest.schema.json"
    path.write_text(json.dumps(MANIFEST_SCHEMA), encoding="utf-8")


def test_stable_hash_is_deterministic() -> None:
    a = stable_hash(dataset_revision="abc123", sample_identity="id:42", seed="seed-v1")
    b = stable_hash(dataset_revision="abc123", sample_identity="id:42", seed="seed-v1")
    assert a == b
    assert len(a) == 64
    assert bytes.fromhex(a) == stable_hash_bytes(
        dataset_revision="abc123", sample_identity="id:42", seed="seed-v1"
    )


def test_manifest_loader_expands_minimal_jsonl_to_internal_model(tmp_repo: Path) -> None:
    _write_schema(tmp_repo)
    manifest = tmp_repo / "evaluation" / "manifests" / "smoke.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "dataset_id": "dataset-a",
                "count": 3,
                "seed": "seed-a",
                "min_duration_sec": 1.0,
                "max_duration_sec": 10.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    entries = ManifestLoader(tmp_repo).load(manifest)
    assert len(entries) == 1
    assert entries[0].id == "dataset-a-001"
    assert entries[0].selection.strategy == "stable_hash"
    assert entries[0].selection.count == 3
    assert entries[0].selection.seed == "seed-a"
    assert entries[0].tags == ()
    assert entries[0].filters.accepts(1.0)
    assert not entries[0].filters.accepts(10.0)


def test_duration_bounds_are_optional(tmp_repo: Path) -> None:
    _write_schema(tmp_repo)
    manifest = tmp_repo / "evaluation" / "manifests" / "full.jsonl"
    manifest.write_text(
        json.dumps({"dataset_id": "dataset-a", "count": 2, "seed": "all"}) + "\n",
        encoding="utf-8",
    )
    entry = ManifestLoader(tmp_repo).load(manifest)[0]
    assert entry.filters.accepts(0.0)
    assert entry.filters.accepts(100000.0)


def test_line_number_makes_derived_entry_ids_unique(tmp_repo: Path) -> None:
    _write_schema(tmp_repo)
    item = {"dataset_id": "dataset-a", "count": 1, "seed": "seed"}
    manifest = tmp_repo / "evaluation" / "manifests" / "duplicate.jsonl"
    manifest.write_text(json.dumps(item) + "\n" + json.dumps(item) + "\n", encoding="utf-8")
    entries = ManifestLoader(tmp_repo).load(manifest)
    assert [entry.id for entry in entries] == ["dataset-a-001", "dataset-a-002"]


def test_old_nested_manifest_shape_is_rejected(tmp_repo: Path) -> None:
    _write_schema(tmp_repo)
    manifest = tmp_repo / "evaluation" / "manifests" / "legacy.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "legacy",
                "dataset_id": "dataset-a",
                "selection": {"strategy": "stable_hash", "count": 1, "seed": "seed"},
                "filters": {"min_duration_sec": 0.0, "max_duration_sec": 5.0},
                "tags": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetManifestError, match="schema violation"):
        ManifestLoader(tmp_repo).load(manifest)
