from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from parakeet_onnx.contracts import (
    ArtifactIdentity,
    CatalogReference,
    ConfigSnapshot,
    ContractError,
    DatasetRevisionEntry,
    DatasetsRevisionSnapshot,
    EvaluationSchemaRevisionSnapshot,
    GitIdentity,
    HostIdentity,
    ReferenceRevisionSnapshot,
    RepoRevisionIdentity,
    RevisionSnapshot,
    RunContext,
    RuntimeIdentity,
    RuntimeRevisionSnapshot,
    reject_nulls,
)
from parakeet_onnx.generated_candidate_io import parse_generated_candidate_contract


def _object(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def _exact(
    value: Mapping[str, Any],
    *,
    name: str,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        raise ContractError(f"{name} is missing required fields: {missing!r}")
    if unknown:
        raise ContractError(f"{name} contains unknown fields: {unknown!r}")


def _string(value: Mapping[str, Any], key: str, *, name: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ContractError(f"{name}.{key} must be a non-empty string")
    return item


def _boolean(value: Mapping[str, Any], key: str, *, name: str) -> bool:
    item = value.get(key)
    if type(item) is not bool:
        raise ContractError(f"{name}.{key} must be a boolean")
    return item


def _positive_int(value: Mapping[str, Any], key: str, *, name: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool) or item <= 0:
        raise ContractError(f"{name}.{key} must be a positive integer")
    return item


def _repo_revision(value: Any, *, name: str) -> RepoRevisionIdentity:
    raw = _object(value, name=name)
    _exact(raw, name=name, required={"repo_id", "revision"})
    return RepoRevisionIdentity(
        repo_id=_string(raw, "repo_id", name=name),
        revision=_string(raw, "revision", name=name),
    )


def parse_revision_snapshot(value: Any) -> RevisionSnapshot:
    raw = _object(value, name="revisions")
    _exact(
        raw,
        name="revisions",
        required={
            "config_version",
            "bundle_sha256",
            "runtime",
            "reference",
            "evaluation_schema",
            "datasets",
        },
    )

    runtime_raw = _object(raw["runtime"], name="revisions.runtime")
    _exact(
        runtime_raw,
        name="revisions.runtime",
        required={"document_sha256", "catalog", "profile_set"},
    )
    catalog_raw = _object(runtime_raw["catalog"], name="revisions.runtime.catalog")
    _exact(
        catalog_raw,
        name="revisions.runtime.catalog",
        required={"id", "sha256"},
    )

    reference_raw = _object(raw["reference"], name="revisions.reference")
    _exact(
        reference_raw,
        name="revisions.reference",
        required={
            "document_sha256",
            "development_artifact",
            "upstream",
            "tokenizer",
            "reference_id",
            "reference_revision",
            "canonical_framework",
        },
    )

    evaluation_raw = _object(
        raw["evaluation_schema"], name="revisions.evaluation_schema"
    )
    _exact(
        evaluation_raw,
        name="revisions.evaluation_schema",
        required={"document_sha256", "schema_id", "schema_revision"},
    )

    datasets_raw = _object(raw["datasets"], name="revisions.datasets")
    _exact(
        datasets_raw,
        name="revisions.datasets",
        required={"document_sha256", "entries"},
    )
    entries_raw = datasets_raw["entries"]
    if not isinstance(entries_raw, list):
        raise ContractError("revisions.datasets.entries must be an array")
    entries: list[DatasetRevisionEntry] = []
    for index, item in enumerate(entries_raw):
        name = f"revisions.datasets.entries[{index}]"
        entry_raw = _object(item, name=name)
        _exact(
            entry_raw,
            name=name,
            required={"id", "repo_id", "revision", "subset", "split", "sha256", "manifest"},
        )
        entries.append(
            DatasetRevisionEntry(
                id=_string(entry_raw, "id", name=name),
                repo_id=_string(entry_raw, "repo_id", name=name),
                revision=_string(entry_raw, "revision", name=name),
                subset=_string(entry_raw, "subset", name=name),
                split=_string(entry_raw, "split", name=name),
                sha256=_string(entry_raw, "sha256", name=name),
                manifest=_string(entry_raw, "manifest", name=name),
            )
        )

    snapshot = RevisionSnapshot(
        config_version=_string(raw, "config_version", name="revisions"),
        bundle_sha256=_string(raw, "bundle_sha256", name="revisions"),
        runtime=RuntimeRevisionSnapshot(
            document_sha256=_string(
                runtime_raw, "document_sha256", name="revisions.runtime"
            ),
            catalog=CatalogReference(
                id=_string(catalog_raw, "id", name="revisions.runtime.catalog"),
                sha256=_string(
                    catalog_raw, "sha256", name="revisions.runtime.catalog"
                ),
            ),
            profile_set=_string(runtime_raw, "profile_set", name="revisions.runtime"),
        ),
        reference=ReferenceRevisionSnapshot(
            document_sha256=_string(
                reference_raw, "document_sha256", name="revisions.reference"
            ),
            development_artifact=_repo_revision(
                reference_raw["development_artifact"],
                name="revisions.reference.development_artifact",
            ),
            upstream=_repo_revision(
                reference_raw["upstream"], name="revisions.reference.upstream"
            ),
            tokenizer=_repo_revision(
                reference_raw["tokenizer"], name="revisions.reference.tokenizer"
            ),
            reference_id=_string(
                reference_raw, "reference_id", name="revisions.reference"
            ),
            reference_revision=_string(
                reference_raw, "reference_revision", name="revisions.reference"
            ),
            canonical_framework=_string(
                reference_raw, "canonical_framework", name="revisions.reference"
            ),
        ),
        evaluation_schema=EvaluationSchemaRevisionSnapshot(
            document_sha256=_string(
                evaluation_raw,
                "document_sha256",
                name="revisions.evaluation_schema",
            ),
            schema_id=_string(
                evaluation_raw, "schema_id", name="revisions.evaluation_schema"
            ),
            schema_revision=_string(
                evaluation_raw,
                "schema_revision",
                name="revisions.evaluation_schema",
            ),
        ),
        datasets=DatasetsRevisionSnapshot(
            document_sha256=_string(
                datasets_raw, "document_sha256", name="revisions.datasets"
            ),
            entries=tuple(entries),
        ),
    )
    snapshot.validate()
    return snapshot


def parse_run_context(value: Any) -> RunContext:
    reject_nulls(value)
    raw = _object(value, name="run-context")
    _exact(
        raw,
        name="run-context",
        required={
            "schema_version",
            "run_id",
            "created_at",
            "config_identity",
            "model_id",
            "environment_id",
            "provider_id",
            "evaluation_id",
            "artifact",
            "git",
            "host",
            "runtime",
            "revisions",
            "config",
            "metadata",
        },
    )
    schema_version = raw["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ContractError("run-context.schema_version must be an integer")

    artifact_raw = _object(raw["artifact"], name="run-context.artifact")
    _exact(
        artifact_raw,
        name="run-context.artifact",
        required={"path", "sha256", "size_bytes", "candidate_id", "artifact_role"},
    )
    git_raw = _object(raw["git"], name="run-context.git")
    _exact(
        git_raw,
        name="run-context.git",
        required={"repository", "commit", "ref", "dirty"},
    )
    host_raw = _object(raw["host"], name="run-context.host")
    _exact(
        host_raw,
        name="run-context.host",
        required={
            "os",
            "architecture",
            "hostname",
            "python_version",
            "implementation",
            "is_wsl",
            "github_runner_os",
            "github_runner_arch",
            "github_run_id",
            "github_run_attempt",
        },
    )
    runtime_raw = _object(raw["runtime"], name="run-context.runtime")
    _exact(
        runtime_raw,
        name="run-context.runtime",
        required={
            "implementation",
            "backend",
            "backend_version",
            "provider_id",
            "provider_ort_name",
            "provider_available",
        },
    )
    config_raw = _object(raw["config"], name="run-context.config")
    _exact(
        config_raw,
        name="run-context.config",
        required={"identity", "sources", "resolved"},
    )
    sources_raw = _object(config_raw["sources"], name="run-context.config.sources")
    _exact(
        sources_raw,
        name="run-context.config.sources",
        required={"model", "provider", "environment", "evaluation"},
    )
    resolved_raw = _object(config_raw["resolved"], name="run-context.config.resolved")
    metadata_raw = _object(raw["metadata"], name="run-context.metadata")

    context = RunContext(
        schema_version=schema_version,
        run_id=_string(raw, "run_id", name="run-context"),
        created_at=_string(raw, "created_at", name="run-context"),
        config_identity=_string(raw, "config_identity", name="run-context"),
        model_id=_string(raw, "model_id", name="run-context"),
        environment_id=_string(raw, "environment_id", name="run-context"),
        provider_id=_string(raw, "provider_id", name="run-context"),
        evaluation_id=_string(raw, "evaluation_id", name="run-context"),
        artifact=ArtifactIdentity(
            path=_string(artifact_raw, "path", name="run-context.artifact"),
            sha256=_string(artifact_raw, "sha256", name="run-context.artifact"),
            size_bytes=_positive_int(
                artifact_raw, "size_bytes", name="run-context.artifact"
            ),
            candidate_id=_string(
                artifact_raw, "candidate_id", name="run-context.artifact"
            ),
            artifact_role=_string(
                artifact_raw, "artifact_role", name="run-context.artifact"
            ),
        ),
        git=GitIdentity(
            repository=_string(git_raw, "repository", name="run-context.git"),
            commit=_string(git_raw, "commit", name="run-context.git"),
            ref=_string(git_raw, "ref", name="run-context.git"),
            dirty=_boolean(git_raw, "dirty", name="run-context.git"),
        ),
        host=HostIdentity(
            os=_string(host_raw, "os", name="run-context.host"),
            architecture=_string(
                host_raw, "architecture", name="run-context.host"
            ),
            hostname=_string(host_raw, "hostname", name="run-context.host"),
            python_version=_string(
                host_raw, "python_version", name="run-context.host"
            ),
            implementation=_string(
                host_raw, "implementation", name="run-context.host"
            ),
            is_wsl=_boolean(host_raw, "is_wsl", name="run-context.host"),
            github_runner_os=_string(
                host_raw, "github_runner_os", name="run-context.host"
            ),
            github_runner_arch=_string(
                host_raw, "github_runner_arch", name="run-context.host"
            ),
            github_run_id=_string(
                host_raw, "github_run_id", name="run-context.host"
            ),
            github_run_attempt=_string(
                host_raw, "github_run_attempt", name="run-context.host"
            ),
        ),
        runtime=RuntimeIdentity(
            implementation=_string(
                runtime_raw, "implementation", name="run-context.runtime"
            ),
            backend=_string(runtime_raw, "backend", name="run-context.runtime"),
            backend_version=_string(
                runtime_raw, "backend_version", name="run-context.runtime"
            ),
            provider_id=_string(
                runtime_raw, "provider_id", name="run-context.runtime"
            ),
            provider_ort_name=_string(
                runtime_raw, "provider_ort_name", name="run-context.runtime"
            ),
            provider_available=_boolean(
                runtime_raw, "provider_available", name="run-context.runtime"
            ),
        ),
        revisions=parse_revision_snapshot(raw["revisions"]),
        config=ConfigSnapshot(
            identity=_string(config_raw, "identity", name="run-context.config"),
            sources={
                key: _string(sources_raw, key, name="run-context.config.sources")
                for key in ("model", "provider", "environment", "evaluation")
            },
            resolved=dict(resolved_raw),
        ),
        metadata=dict(metadata_raw),
    )
    context.validate()
    parse_generated_candidate_contract(context.metadata.get("candidate"))
    return context


def load_run_context(path: str | Path) -> RunContext:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid run-context JSON: {source}: {exc}") from exc
    return parse_run_context(value)
