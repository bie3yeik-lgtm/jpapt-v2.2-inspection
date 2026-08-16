from __future__ import annotations

import hashlib
import json

import pytest

from parakeet_onnx.evaluation import (
    CapsuleArtifactError,
    EmbeddedCapsuleArtifact,
    ExternalCapsuleArtifact,
    ExperimentCapsuleError,
    read_experiment_capsule,
)
from parakeet_onnx.evaluation.parquet import (
    _atomic_write_parquet,
    build_experiment_capsule_rows,
)


def _benchmark() -> dict[str, object]:
    return {
        "run_id": "run-artifact",
        "samples": {"attempted": 0},
        "quality": {},
        "performance": {},
        "memory": {},
        "parity": {},
        "provider": {},
        "errors": {},
    }


def test_embedded_artifact_chunks_and_extracts(tmp_path) -> None:
    payload = b"abcdefghij"
    artifact = EmbeddedCapsuleArtifact(
        artifact_id="profile",
        name="profile.json",
        mime_type="application/json",
        payload=payload,
        metadata={"role": "diagnostic"},
        chunk_size_bytes=4,
    )
    rows = build_experiment_capsule_rows(
        run_context={"run_id": "run-artifact"},
        samples=[],
        benchmark=_benchmark(),
        artifacts=[artifact],
    )
    path = tmp_path / "run.parquet"
    _atomic_write_parquet(path, rows)

    capsule = read_experiment_capsule(path)
    assert capsule.artifact_ids() == ("profile",)
    assert len(capsule.artifacts) == 3
    assert capsule.artifact_metadata("profile")["role"] == "diagnostic"

    destination = capsule.extract_artifact("profile", tmp_path / "out" / "profile.json")
    assert destination.read_bytes() == payload


def test_external_artifact_is_reference_only(tmp_path) -> None:
    digest = hashlib.sha256(b"model").hexdigest()
    artifact = ExternalCapsuleArtifact(
        artifact_id="model",
        name="model.onnx",
        mime_type="application/octet-stream",
        uri="hf://buckets/example/models/model.onnx",
        sha256=digest,
        size_bytes=5,
    )
    rows = build_experiment_capsule_rows(
        run_context={"run_id": "run-artifact"},
        samples=[],
        benchmark=_benchmark(),
        artifacts=[artifact],
    )
    path = tmp_path / "run.parquet"
    _atomic_write_parquet(path, rows)

    capsule = read_experiment_capsule(path)
    metadata = capsule.artifact_metadata("model")
    assert metadata["location"] == "external"
    assert metadata["uri"].startswith("hf://buckets/")
    assert capsule.artifacts[0]["payload"] is None
    with pytest.raises(ExperimentCapsuleError, match="external"):
        capsule.extract_artifact("model", tmp_path / "model.onnx")


def test_embedded_artifact_rejects_oversized_payload() -> None:
    artifact = EmbeddedCapsuleArtifact(
        artifact_id="too-large",
        name="too-large.bin",
        mime_type="application/octet-stream",
        payload=b"x" * (8 * 1024 * 1024 + 1),
    )
    with pytest.raises(CapsuleArtifactError, match="bounded Python writer limit"):
        list(artifact.iter_parts())


def test_artifact_rows_preserve_deterministic_metadata_json() -> None:
    artifact = EmbeddedCapsuleArtifact(
        artifact_id="report",
        name="report.md",
        mime_type="text/markdown",
        payload=b"report",
        metadata={"z": 1, "a": 2},
    )
    rows = build_experiment_capsule_rows(
        run_context={"run_id": "run-artifact"},
        samples=[],
        benchmark=_benchmark(),
        artifacts=[artifact],
    )
    artifact_row = next(row for row in rows if row["record_kind"] == "artifact")
    metadata = json.loads(artifact_row["metadata_json"])
    assert metadata == {"a": 2, "location": "embedded", "z": 1}
