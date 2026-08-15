from __future__ import annotations

import json
from pathlib import Path

import pytest

from parakeet_onnx.datasets.errors import DatasetManifestError
from parakeet_onnx.datasets.manifest import (
    ManifestLoader,
    stable_hash,
    stable_hash_bytes,
)


MANIFEST_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "id",
        "dataset_id",
        "selection",
        "filters",
        "tags",
    ],
    "properties": {
        "schema_version": {"const": 1},
        "id": {"type": "string"},
        "dataset_id": {"type": "string"},
        "selection": {
            "type": "object",
            "required": ["strategy", "count", "seed"],
            "properties": {
                "strategy": {"const": "stable_hash"},
                "count": {"type": "integer", "minimum": 1},
                "seed": {"type": "string", "minLength": 1},
            },
        },
        "filters": {
            "type": "object",
            "required": ["min_duration_sec", "max_duration_sec"],
            "properties": {
                "min_duration_sec": {"type": "number", "minimum": 0},
                "max_duration_sec": {"type": "number", "exclusiveMinimum": 0},
            },
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
        },
    },
}


def _write_schema(root: Path) -> None:
    path = root / "evaluation" / "schemas" / "manifest.schema.json"
    path.write_text(
        json.dumps(MANIFEST_SCHEMA),
        encoding="utf-8",
    )


def test_stable_hash_is_deterministic() -> None:
    a = stable_hash(
        dataset_revision="abc123",
        sample_identity="id:42",
        seed="seed-v1",
    )
    b = stable_hash(
        dataset_revision="abc123",
        sample_identity="id:42",
        seed="seed-v1",
    )

    assert a == b
    assert len(a) == 64
    assert bytes.fromhex(a) == stable_hash_bytes(
        dataset_revision="abc123",
        sample_identity="id:42",
        seed="seed-v1",
    )


def test_stable_hash_changes_when_revision_changes() -> None:
    a = stable_hash(
        dataset_revision="rev-a",
        sample_identity="id:42",
        seed="seed-v1",
    )
    b = stable_hash(
        dataset_revision="rev-b",
        sample_identity="id:42",
        seed="seed-v1",
    )

    assert a != b


def test_manifest_loader_loads_valid_jsonl(tmp_repo: Path) -> None:
    _write_schema(tmp_repo)

    manifest = tmp_repo / "evaluation" / "manifests" / "smoke.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "smoke-a",
                "dataset_id": "dataset-a",
                "selection": {
                    "strategy": "stable_hash",
                    "count": 3,
                    "seed": "seed-a",
                },
                "filters": {
                    "min_duration_sec": 1.0,
                    "max_duration_sec": 10.0,
                },
                "tags": ["smoke"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    loader = ManifestLoader(tmp_repo)
    entries = loader.load(manifest)

    assert len(entries) == 1
    assert entries[0].id == "smoke-a"
    assert entries[0].selection.count == 3


def test_manifest_loader_rejects_duplicate_ids(tmp_repo: Path) -> None:
    _write_schema(tmp_repo)

    item = {
        "schema_version": 1,
        "id": "duplicate",
        "dataset_id": "dataset-a",
        "selection": {
            "strategy": "stable_hash",
            "count": 1,
            "seed": "seed",
        },
        "filters": {
            "min_duration_sec": 0.0,
            "max_duration_sec": 5.0,
        },
        "tags": [],
    }

    manifest = tmp_repo / "evaluation" / "manifests" / "duplicate.jsonl"
    manifest.write_text(
        json.dumps(item) + "\n" + json.dumps(item) + "\n",
        encoding="utf-8",
    )

    loader = ManifestLoader(tmp_repo)

    with pytest.raises(DatasetManifestError):
        loader.load(manifest)
