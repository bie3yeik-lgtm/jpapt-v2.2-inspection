from __future__ import annotations

import pytest

from parakeet_onnx.contracts import (
    ContractError,
    DatasetRevisionEntry,
    DatasetsRevisionSnapshot,
    RevisionSnapshot,
    RuntimeRevisionSnapshot,
    CatalogReference,
    ReferenceRevisionSnapshot,
    RepoRevisionIdentity,
    EvaluationSchemaRevisionSnapshot,
    reject_nulls,
)


SHA = "a" * 64


def _snapshot() -> RevisionSnapshot:
    repo = RepoRevisionIdentity(repo_id="example/repo", revision="deadbeef")
    return RevisionSnapshot(
        config_version="config-000001",
        bundle_sha256=SHA,
        runtime=RuntimeRevisionSnapshot(
            document_sha256=SHA,
            catalog=CatalogReference(id="asr-runtime-catalog-v1", sha256=SHA),
            profile_set="parakeet-tdt-ctc-v1",
        ),
        reference=ReferenceRevisionSnapshot(
            document_sha256=SHA,
            development_artifact=repo,
            upstream=repo,
            tokenizer=repo,
            reference_id="reference-v1",
            reference_revision="deadbeef",
            canonical_framework="nemo",
        ),
        evaluation_schema=EvaluationSchemaRevisionSnapshot(
            document_sha256=SHA,
            schema_id="asr-evaluation-v1",
            schema_revision="deadbeef",
        ),
        datasets=DatasetsRevisionSnapshot(
            document_sha256=SHA,
            entries=(
                DatasetRevisionEntry(
                    id="jsut",
                    repo_id="japanese-asr/ja_asr.jsut_basic5000",
                    revision="deadbeef",
                    subset="default",
                    split="test",
                    sha256=SHA,
                    manifest="evaluation/manifests/smoke.json",
                ),
            ),
        ),
    )


def test_revision_snapshot_rejects_noncanonical_config_version() -> None:
    value = _snapshot()
    object.__setattr__(value, "config_version", "unversioned")
    with pytest.raises(ContractError, match="config-NNNNNN"):
        value.validate()


def test_recursive_null_rejection_reports_path() -> None:
    with pytest.raises(ContractError, match=r"\$\.metadata\.candidate\.tokenizer"):
        reject_nulls({"metadata": {"candidate": {"tokenizer": None}}})


def test_revision_snapshot_is_null_free() -> None:
    value = _snapshot()
    value.validate()
    assert value.to_dict()["datasets"]["entries"][0]["sha256"] == SHA
