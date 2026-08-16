from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping


RUN_CONTEXT_SCHEMA_VERSION = 2
GENERATED_CANDIDATE_SCHEMA_VERSION = 1

_ENVIRONMENTS = frozenset({"linux", "windows", "macos"})
_PROVIDERS = frozenset({"cpu", "cuda", "directml", "coreml"})
_EVALUATIONS = frozenset({"smoke", "parity", "coreml-parity", "full"})
_IMPLEMENTATIONS = frozenset({"python", "rust"})
_BACKENDS = frozenset({"onnxruntime"})
_DECODERS = frozenset({"ctc", "tdt", "whisper_autoregressive"})
_INPUT_KINDS = frozenset({"canonical_waveform", "features"})
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_GIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_CONFIG_VERSION_RE = re.compile(r"^config-\d{6}$")


class ContractError(RuntimeError):
    pass


def require_nonempty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be a non-empty string")
    return value


def require_sha256(name: str, value: str) -> str:
    require_nonempty(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise ContractError(f"{name} must be a 64-character SHA-256")
    return value.lower()


def require_git_commit(value: str) -> str:
    require_nonempty("git.commit", value)
    if _GIT_RE.fullmatch(value) is None:
        raise ContractError("git.commit must be a 7-64 character hexadecimal commit identity")
    return value.lower()


def require_config_version(value: str) -> str:
    require_nonempty("revisions.config_version", value)
    if _CONFIG_VERSION_RE.fullmatch(value) is None:
        raise ContractError("revisions.config_version must match config-NNNNNN")
    return value


def require_one_of(name: str, value: str, allowed: frozenset[str]) -> str:
    require_nonempty(name, value)
    if value not in allowed:
        raise ContractError(
            f"{name} has unsupported value {value!r}; expected one of {sorted(allowed)}"
        )
    return value


def reject_nulls(value: Any, path: str = "$") -> None:
    if value is None:
        raise ContractError(f"contract must not contain null: {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            reject_nulls(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_nulls(item, f"{path}[{index}]")


@dataclass(frozen=True, slots=True)
class GeneratedCatalog:
    id: str
    sha256: str

    def validate(self) -> None:
        require_nonempty("candidate.catalog.id", self.id)
        require_sha256("candidate.catalog.sha256", self.sha256)


@dataclass(frozen=True, slots=True)
class GeneratedArtifact:
    path: str
    sha256: str
    size_bytes: int

    def validate(self, role: str) -> None:
        require_nonempty(f"candidate.artifacts.{role}.path", self.path)
        require_sha256(f"candidate.artifacts.{role}.sha256", self.sha256)
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool) or self.size_bytes <= 0:
            raise ContractError(
                f"candidate.artifacts.{role}.size_bytes must be a positive integer"
            )


@dataclass(frozen=True, slots=True)
class GeneratedTokenizer:
    kind: str
    path: str

    def validate(self) -> None:
        require_nonempty("candidate.tokenizer.kind", self.kind)
        require_nonempty("candidate.tokenizer.path", self.path)


@dataclass(frozen=True, slots=True)
class GeneratedRuntimeContract:
    decoder: str
    input_kind: str
    io: Mapping[str, Any]
    decoder_config: Mapping[str, Any]

    def validate(self) -> None:
        require_one_of("candidate.runtime_contract.decoder", self.decoder, _DECODERS)
        require_one_of("candidate.runtime_contract.input_kind", self.input_kind, _INPUT_KINDS)
        reject_nulls(self.io, "$.runtime_contract.io")
        reject_nulls(self.decoder_config, "$.runtime_contract.decoder_config")


@dataclass(frozen=True, slots=True)
class GeneratedCandidateContract:
    schema_version: int
    candidate_root: str
    candidate_id: str
    profile_set: str
    variant: str
    profile: str
    decoder: str
    artifact_contract: str
    catalog: GeneratedCatalog
    bundle_sha256: str
    artifacts: Mapping[str, GeneratedArtifact]
    tokenizer: GeneratedTokenizer | None
    features: Mapping[str, bool]
    runtime_contract: GeneratedRuntimeContract

    def validate(self) -> None:
        if self.schema_version != GENERATED_CANDIDATE_SCHEMA_VERSION:
            raise ContractError(
                f"generated candidate schema_version must equal {GENERATED_CANDIDATE_SCHEMA_VERSION}"
            )
        for name, value in (
            ("candidate_root", self.candidate_root),
            ("candidate_id", self.candidate_id),
            ("profile_set", self.profile_set),
            ("variant", self.variant),
            ("profile", self.profile),
            ("artifact_contract", self.artifact_contract),
        ):
            require_nonempty(f"candidate.{name}", value)
        require_one_of("candidate.decoder", self.decoder, _DECODERS)
        require_sha256("candidate.bundle_sha256", self.bundle_sha256)
        self.catalog.validate()
        if self.decoder != self.runtime_contract.decoder:
            raise ContractError(
                "candidate.decoder must equal candidate.runtime_contract.decoder"
            )
        if not self.artifacts:
            raise ContractError("candidate.artifacts must not be empty")
        for role, artifact in self.artifacts.items():
            require_nonempty("candidate artifact role", role)
            artifact.validate(role)
        if self.tokenizer is not None:
            self.tokenizer.validate()
        for key, value in self.features.items():
            require_nonempty("candidate feature name", key)
            if type(value) is not bool:
                raise ContractError(f"candidate.features.{key} must be boolean")
        self.runtime_contract.validate()
        reject_nulls(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": self.schema_version,
            "candidate_root": self.candidate_root,
            "candidate_id": self.candidate_id,
            "profile_set": self.profile_set,
            "variant": self.variant,
            "profile": self.profile,
            "decoder": self.decoder,
            "artifact_contract": self.artifact_contract,
            "catalog": asdict(self.catalog),
            "bundle_sha256": self.bundle_sha256,
            "artifacts": {
                role: asdict(artifact)
                for role, artifact in sorted(self.artifacts.items())
            },
            "features": dict(sorted(self.features.items())),
            "runtime_contract": {
                "decoder": self.runtime_contract.decoder,
                "input_kind": self.runtime_contract.input_kind,
                "io": dict(self.runtime_contract.io),
                "decoder_config": dict(self.runtime_contract.decoder_config),
            },
        }
        if self.tokenizer is not None:
            value["tokenizer"] = asdict(self.tokenizer)
        return value


@dataclass(frozen=True, slots=True)
class CatalogReference:
    id: str
    sha256: str

    def validate(self) -> None:
        require_nonempty("revisions.runtime.catalog.id", self.id)
        require_sha256("revisions.runtime.catalog.sha256", self.sha256)


@dataclass(frozen=True, slots=True)
class RepoRevisionIdentity:
    repo_id: str
    revision: str

    def validate(self, name: str) -> None:
        require_nonempty(f"{name}.repo_id", self.repo_id)
        require_nonempty(f"{name}.revision", self.revision)


@dataclass(frozen=True, slots=True)
class RuntimeRevisionSnapshot:
    document_sha256: str
    catalog: CatalogReference
    profile_set: str

    def validate(self) -> None:
        require_sha256("revisions.runtime.document_sha256", self.document_sha256)
        self.catalog.validate()
        require_nonempty("revisions.runtime.profile_set", self.profile_set)


@dataclass(frozen=True, slots=True)
class ReferenceRevisionSnapshot:
    document_sha256: str
    development_artifact: RepoRevisionIdentity
    upstream: RepoRevisionIdentity
    tokenizer: RepoRevisionIdentity
    reference_id: str
    reference_revision: str
    canonical_framework: str

    def validate(self) -> None:
        require_sha256("revisions.reference.document_sha256", self.document_sha256)
        self.development_artifact.validate("revisions.reference.development_artifact")
        self.upstream.validate("revisions.reference.upstream")
        self.tokenizer.validate("revisions.reference.tokenizer")
        require_nonempty("revisions.reference.reference_id", self.reference_id)
        require_nonempty("revisions.reference.reference_revision", self.reference_revision)
        require_nonempty("revisions.reference.canonical_framework", self.canonical_framework)


@dataclass(frozen=True, slots=True)
class EvaluationSchemaRevisionSnapshot:
    document_sha256: str
    schema_id: str
    schema_revision: str

    def validate(self) -> None:
        require_sha256("revisions.evaluation_schema.document_sha256", self.document_sha256)
        require_nonempty("revisions.evaluation_schema.schema_id", self.schema_id)
        require_nonempty("revisions.evaluation_schema.schema_revision", self.schema_revision)


@dataclass(frozen=True, slots=True)
class DatasetRevisionEntry:
    id: str
    repo_id: str
    revision: str
    subset: str
    split: str
    sha256: str
    manifest: str

    def validate(self, index: int) -> None:
        prefix = f"revisions.datasets.entries[{index}]"
        require_nonempty(f"{prefix}.id", self.id)
        require_nonempty(f"{prefix}.repo_id", self.repo_id)
        require_nonempty(f"{prefix}.revision", self.revision)
        require_nonempty(f"{prefix}.subset", self.subset)
        require_nonempty(f"{prefix}.split", self.split)
        require_sha256(f"{prefix}.sha256", self.sha256)
        require_nonempty(f"{prefix}.manifest", self.manifest)


@dataclass(frozen=True, slots=True)
class DatasetsRevisionSnapshot:
    document_sha256: str
    entries: tuple[DatasetRevisionEntry, ...]

    def validate(self) -> None:
        require_sha256("revisions.datasets.document_sha256", self.document_sha256)
        ids: set[str] = set()
        for index, entry in enumerate(self.entries):
            entry.validate(index)
            if entry.id in ids:
                raise ContractError(f"duplicate dataset revision id: {entry.id}")
            ids.add(entry.id)


@dataclass(frozen=True, slots=True)
class RevisionSnapshot:
    config_version: str
    bundle_sha256: str
    runtime: RuntimeRevisionSnapshot
    reference: ReferenceRevisionSnapshot
    evaluation_schema: EvaluationSchemaRevisionSnapshot
    datasets: DatasetsRevisionSnapshot

    def validate(self) -> None:
        require_config_version(self.config_version)
        require_sha256("revisions.bundle_sha256", self.bundle_sha256)
        self.runtime.validate()
        self.reference.validate()
        self.evaluation_schema.validate()
        self.datasets.validate()
        reject_nulls(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    path: str
    sha256: str
    size_bytes: int
    candidate_id: str
    artifact_role: str

    def validate(self) -> None:
        require_nonempty("artifact.path", self.path)
        require_sha256("artifact.sha256", self.sha256)
        require_nonempty("artifact.candidate_id", self.candidate_id)
        require_nonempty("artifact.artifact_role", self.artifact_role)
        if self.size_bytes <= 0:
            raise ContractError("artifact.size_bytes must be greater than zero")


@dataclass(frozen=True, slots=True)
class GitIdentity:
    repository: str
    commit: str
    ref: str
    dirty: bool

    def validate(self) -> None:
        require_nonempty("git.repository", self.repository)
        require_git_commit(self.commit)
        require_nonempty("git.ref", self.ref)
        if type(self.dirty) is not bool:
            raise ContractError("git.dirty must be boolean")


@dataclass(frozen=True, slots=True)
class HostIdentity:
    os: str
    architecture: str
    hostname: str
    python_version: str
    implementation: str
    is_wsl: bool
    github_runner_os: str
    github_runner_arch: str
    github_run_id: str
    github_run_attempt: str

    def validate(self) -> None:
        for name, value in (
            ("host.os", self.os),
            ("host.architecture", self.architecture),
            ("host.hostname", self.hostname),
            ("host.python_version", self.python_version),
            ("host.implementation", self.implementation),
            ("host.github_runner_os", self.github_runner_os),
            ("host.github_runner_arch", self.github_runner_arch),
            ("host.github_run_id", self.github_run_id),
            ("host.github_run_attempt", self.github_run_attempt),
        ):
            require_nonempty(name, value)
        if type(self.is_wsl) is not bool:
            raise ContractError("host.is_wsl must be boolean")


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    implementation: str
    backend: str
    backend_version: str
    provider_id: str
    provider_ort_name: str
    provider_available: bool

    def validate(self) -> None:
        require_one_of("runtime.implementation", self.implementation, _IMPLEMENTATIONS)
        require_one_of("runtime.backend", self.backend, _BACKENDS)
        require_nonempty("runtime.backend_version", self.backend_version)
        require_one_of("runtime.provider_id", self.provider_id, _PROVIDERS)
        require_nonempty("runtime.provider_ort_name", self.provider_ort_name)
        if type(self.provider_available) is not bool:
            raise ContractError("runtime.provider_available must be boolean")


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    identity: str
    sources: Mapping[str, str]
    resolved: Mapping[str, Any]

    def validate(self) -> None:
        require_nonempty("config.identity", self.identity)
        for required in ("model", "provider", "environment", "evaluation"):
            value = self.sources.get(required)
            require_nonempty(f"config.sources.{required}", value if isinstance(value, str) else "")
        reject_nulls(self.resolved, "$.config.resolved")


@dataclass(frozen=True, slots=True)
class RunContext:
    schema_version: int
    run_id: str
    created_at: str
    config_identity: str
    model_id: str
    environment_id: str
    provider_id: str
    evaluation_id: str
    artifact: ArtifactIdentity
    git: GitIdentity
    host: HostIdentity
    runtime: RuntimeIdentity
    revisions: RevisionSnapshot
    config: ConfigSnapshot
    metadata: Mapping[str, Any]

    def validate(self) -> None:
        if self.schema_version != RUN_CONTEXT_SCHEMA_VERSION:
            raise ContractError(
                f"run-context schema_version must equal {RUN_CONTEXT_SCHEMA_VERSION}"
            )
        for name, value in (
            ("run_id", self.run_id),
            ("created_at", self.created_at),
            ("config_identity", self.config_identity),
            ("model_id", self.model_id),
        ):
            require_nonempty(name, value)
        require_one_of("environment_id", self.environment_id, _ENVIRONMENTS)
        require_one_of("provider_id", self.provider_id, _PROVIDERS)
        require_one_of("evaluation_id", self.evaluation_id, _EVALUATIONS)
        self.artifact.validate()
        self.git.validate()
        self.host.validate()
        self.runtime.validate()
        self.revisions.validate()
        self.config.validate()
        if self.runtime.provider_id != self.provider_id:
            raise ContractError("runtime.provider_id must equal provider_id")
        candidate = self.metadata.get("candidate")
        if not isinstance(candidate, Mapping):
            raise ContractError("metadata.candidate is required")
        if candidate.get("candidate_id") != self.artifact.candidate_id:
            raise ContractError(
                "artifact.candidate_id must equal metadata.candidate.candidate_id"
            )
        if candidate.get("profile_set") != self.revisions.runtime.profile_set:
            raise ContractError(
                "metadata.candidate.profile_set must equal revisions.runtime.profile_set"
            )
        catalog = candidate.get("catalog")
        if not isinstance(catalog, Mapping):
            raise ContractError("metadata.candidate.catalog must be an object")
        if (
            catalog.get("id") != self.revisions.runtime.catalog.id
            or catalog.get("sha256") != self.revisions.runtime.catalog.sha256
        ):
            raise ContractError(
                "metadata.candidate.catalog must equal revisions.runtime.catalog"
            )
        reject_nulls(self.metadata, "$.metadata")
        reject_nulls(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        self.validate()
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )

    def write_json(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_json() + "\n", encoding="utf-8")
