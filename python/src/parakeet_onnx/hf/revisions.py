"""Strict four-document revision loading.

The lock bundle remains human-authored JSON, but every execution snapshot is
materialized as the same non-null typed contract consumed by Rust.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from parakeet_onnx.config.catalog import (
    AsrCatalog,
    AsrCatalogError,
    load_repository_catalog,
)
from parakeet_onnx.contracts import (
    CatalogReference,
    DatasetRevisionEntry,
    DatasetsRevisionSnapshot,
    EvaluationSchemaRevisionSnapshot,
    ReferenceRevisionSnapshot,
    RepoRevisionIdentity,
    RevisionSnapshot,
    RuntimeRevisionSnapshot,
)


class RevisionError(RuntimeError):
    pass


_CONFIG_VERSION_RE = re.compile(r"^config-\d{6}$")


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RevisionError(f"Revision file does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RevisionError(f"Invalid JSON in revision file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RevisionError(f"Revision file root must be a JSON object: {path}")
    if value.get("schema_version") != 1:
        raise RevisionError(f"{path.name}: schema_version must equal 1; got {value.get('schema_version')!r}")
    if _contains_null(value):
        raise RevisionError(f"{path.name}: null values are not allowed in revision documents")
    return value


def _contains_null(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, Mapping):
        return any(_contains_null(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_null(item) for item in value)
    return False


def _load_config_version(root: Path) -> str:
    path = root.parent / "resolved.json"
    if not path.is_file():
        raise RevisionError(
            "resolved.json is required next to revisions/; unversioned revision bundles are unsupported"
        )
    value = _load_json(path)
    config_version = value.get("config_version")
    if not isinstance(config_version, str) or _CONFIG_VERSION_RE.fullmatch(config_version) is None:
        raise RevisionError(f"{path.name}: config_version must match config-NNNNNN; got {config_version!r}")
    return config_version


def _reject_unknown(
    source: Mapping[str, Any],
    allowed: set[str],
    *,
    document: str,
) -> None:
    unknown = sorted(set(source) - allowed)
    if unknown:
        raise RevisionError(f"{document}: unsupported fields are present: {unknown!r}")


def _require_mapping(source: Mapping[str, Any], key: str, *, document: str) -> Mapping[str, Any]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise RevisionError(f"{document}: {key!r} must be an object")
    return value


def _require_string(source: Mapping[str, Any], key: str, *, document: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RevisionError(f"{document}: {key!r} must be a non-empty string")
    return value.strip()


def _optional_string(source: Mapping[str, Any], key: str, *, document: str) -> str | None:
    if key not in source:
        return None
    value = source[key]
    if not isinstance(value, str) or not value.strip():
        raise RevisionError(f"{document}: {key!r} must be a non-empty string when present")
    return value.strip()


def _identity(raw: Mapping[str, Any], key: str, *, document: str) -> tuple[str, str]:
    value = _require_mapping(raw, key, document=document)
    _reject_unknown(value, {"repo_id", "revision"}, document=f"{document}.{key}")
    return (
        _require_string(value, "repo_id", document=f"{document}.{key}"),
        _require_string(value, "revision", document=f"{document}.{key}"),
    )


@dataclass(frozen=True, slots=True)
class RevisionDocument:
    name: str
    path: Path
    raw: dict[str, Any]
    sha256: str

    @classmethod
    def load(cls, *, name: str, path: Path) -> RevisionDocument:
        raw = _load_json(path)
        return cls(
            name=name,
            path=path,
            raw=raw,
            sha256=hashlib.sha256(_canonical_json_bytes(raw)).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class RuntimeRevision:
    document: RevisionDocument
    catalog_id: str
    catalog_sha256: str
    profile_set_id: str
    variants: Mapping[str, str]
    default_variant: str

    @classmethod
    def from_document(cls, document: RevisionDocument, *, catalog: AsrCatalog) -> RuntimeRevision:
        raw = document.raw
        _reject_unknown(
            raw,
            {"schema_version", "catalog", "profile_set"},
            document=document.name,
        )
        catalog_raw = _require_mapping(raw, "catalog", document=document.name)
        _reject_unknown(catalog_raw, {"id", "sha256"}, document=f"{document.name}.catalog")
        catalog_id = _require_string(catalog_raw, "id", document=f"{document.name}.catalog")
        catalog_sha = _require_string(catalog_raw, "sha256", document=f"{document.name}.catalog")
        if catalog_id != catalog.catalog_id:
            raise RevisionError(
                f"runtime.json catalog id mismatch: lock={catalog_id!r}, repository={catalog.catalog_id!r}"
            )
        if catalog_sha.lower() != catalog.sha256.lower():
            raise RevisionError("runtime.json catalog SHA-256 does not match config/asr-catalog.json")
        profile_set_id = _require_string(raw, "profile_set", document=document.name)
        try:
            profile_set = catalog.profile_set(profile_set_id)
        except AsrCatalogError as exc:
            raise RevisionError(str(exc)) from exc
        return cls(
            document=document,
            catalog_id=catalog_id,
            catalog_sha256=catalog_sha.lower(),
            profile_set_id=profile_set_id,
            variants=dict(profile_set.variants),
            default_variant=profile_set.default_variant,
        )

    def resolve_variant(self, variant: str | None, *, catalog: AsrCatalog) -> tuple[str, str, str]:
        selected = variant or self.default_variant
        try:
            profile_id = self.variants[selected]
        except KeyError as exc:
            raise RevisionError(f"unknown runtime variant {selected!r}; available={sorted(self.variants)}") from exc
        profile = catalog.decoder_profile(profile_id)
        return selected, profile_id, profile.decoder


@dataclass(frozen=True, slots=True)
class ReferenceRevision:
    document: RevisionDocument
    development_artifact_repo_id: str
    development_artifact_revision: str
    upstream_repo_id: str
    upstream_revision: str
    tokenizer_repo_id: str
    tokenizer_revision: str
    reference_id: str
    reference_revision: str
    canonical_framework: str

    @classmethod
    def from_document(cls, document: RevisionDocument) -> ReferenceRevision:
        raw = document.raw
        _reject_unknown(
            raw,
            {
                "schema_version",
                "development_artifact",
                "upstream",
                "tokenizer",
                "reference",
            },
            document=document.name,
        )
        development_repo_id, development_revision = _identity(raw, "development_artifact", document=document.name)
        upstream_repo_id, upstream_revision = _identity(raw, "upstream", document=document.name)
        tokenizer_repo_id, tokenizer_revision = _identity(raw, "tokenizer", document=document.name)
        reference = _require_mapping(raw, "reference", document=document.name)
        _reject_unknown(
            reference,
            {"id", "revision", "canonical_framework"},
            document=f"{document.name}.reference",
        )
        return cls(
            document=document,
            development_artifact_repo_id=development_repo_id,
            development_artifact_revision=development_revision,
            upstream_repo_id=upstream_repo_id,
            upstream_revision=upstream_revision,
            tokenizer_repo_id=tokenizer_repo_id,
            tokenizer_revision=tokenizer_revision,
            reference_id=_require_string(reference, "id", document=f"{document.name}.reference"),
            reference_revision=_require_string(reference, "revision", document=f"{document.name}.reference"),
            canonical_framework=_require_string(
                reference,
                "canonical_framework",
                document=f"{document.name}.reference",
            ),
        )


@dataclass(frozen=True, slots=True)
class EvaluationSchemaRevision:
    document: RevisionDocument
    schema_id: str
    schema_revision: str

    @classmethod
    def from_document(cls, document: RevisionDocument) -> EvaluationSchemaRevision:
        raw = document.raw
        _reject_unknown(raw, {"schema_version", "schema"}, document=document.name)
        schema = _require_mapping(raw, "schema", document=document.name)
        _reject_unknown(schema, {"id", "revision"}, document=f"{document.name}.schema")
        return cls(
            document=document,
            schema_id=_require_string(schema, "id", document=f"{document.name}.schema"),
            schema_revision=_require_string(schema, "revision", document=f"{document.name}.schema"),
        )


@dataclass(frozen=True, slots=True)
class DatasetLockEntry:
    id: str
    repo_id: str
    revision: str
    subset: str | None
    split: str | None
    sha256: str | None
    manifest: str | None


@dataclass(frozen=True, slots=True)
class DatasetLock:
    document: RevisionDocument
    datasets: tuple[DatasetLockEntry, ...]

    @classmethod
    def from_document(cls, document: RevisionDocument) -> DatasetLock:
        raw = document.raw
        _reject_unknown(raw, {"schema_version", "datasets"}, document=document.name)
        raw_datasets = raw.get("datasets")
        if not isinstance(raw_datasets, list):
            raise RevisionError(f"{document.name}: 'datasets' must be a JSON array")
        entries: list[DatasetLockEntry] = []
        for index, item in enumerate(raw_datasets):
            if not isinstance(item, dict):
                raise RevisionError(f"{document.name}: datasets[{index}] must be an object")
            _reject_unknown(
                item,
                {"id", "repo_id", "revision", "subset", "split", "sha256", "manifest"},
                document=f"{document.name}.datasets[{index}]",
            )
            entries.append(
                DatasetLockEntry(
                    id=_require_string(item, "id", document=document.name),
                    repo_id=_require_string(item, "repo_id", document=document.name),
                    revision=_require_string(item, "revision", document=document.name),
                    subset=_optional_string(item, "subset", document=f"{document.name}.datasets[{index}]"),
                    split=_optional_string(item, "split", document=f"{document.name}.datasets[{index}]"),
                    sha256=_optional_string(item, "sha256", document=f"{document.name}.datasets[{index}]"),
                    manifest=_optional_string(item, "manifest", document=f"{document.name}.datasets[{index}]"),
                )
            )
        ids = [entry.id for entry in entries]
        if len(ids) != len(set(ids)):
            raise RevisionError(f"{document.name}: duplicate dataset IDs are not allowed")
        return cls(document=document, datasets=tuple(entries))

    def get(self, dataset_id: str) -> DatasetLockEntry:
        for entry in self.datasets:
            if entry.id == dataset_id:
                return entry
        raise RevisionError(f"Dataset is not present in datasets-lock.json: {dataset_id}")


@dataclass(frozen=True, slots=True)
class RevisionBundle:
    reference: ReferenceRevision
    evaluation_schema: EvaluationSchemaRevision
    datasets: DatasetLock
    runtime: RuntimeRevision
    config_version: str

    @property
    def sha256(self) -> str:
        digest = hashlib.sha256()
        for document in (
            self.reference.document,
            self.evaluation_schema.document,
            self.datasets.document,
            self.runtime.document,
        ):
            digest.update(document.sha256.encode("ascii"))
        return digest.hexdigest()

    def snapshot(self) -> RevisionSnapshot:
        entries: list[DatasetRevisionEntry] = []
        for entry in self.datasets.datasets:
            if entry.sha256 is None:
                raise RevisionError(f"datasets-lock entry {entry.id!r} requires sha256 before execution")
            if entry.manifest is None:
                raise RevisionError(f"datasets-lock entry {entry.id!r} requires manifest before execution")
            entries.append(
                DatasetRevisionEntry(
                    id=entry.id,
                    repo_id=entry.repo_id,
                    revision=entry.revision,
                    subset=entry.subset or "default",
                    split=entry.split or "default",
                    sha256=entry.sha256,
                    manifest=entry.manifest,
                )
            )
        value = RevisionSnapshot(
            config_version=self.config_version,
            bundle_sha256=self.sha256,
            runtime=RuntimeRevisionSnapshot(
                document_sha256=self.runtime.document.sha256,
                catalog=CatalogReference(
                    id=self.runtime.catalog_id,
                    sha256=self.runtime.catalog_sha256,
                ),
                profile_set=self.runtime.profile_set_id,
            ),
            reference=ReferenceRevisionSnapshot(
                document_sha256=self.reference.document.sha256,
                development_artifact=RepoRevisionIdentity(
                    repo_id=self.reference.development_artifact_repo_id,
                    revision=self.reference.development_artifact_revision,
                ),
                upstream=RepoRevisionIdentity(
                    repo_id=self.reference.upstream_repo_id,
                    revision=self.reference.upstream_revision,
                ),
                tokenizer=RepoRevisionIdentity(
                    repo_id=self.reference.tokenizer_repo_id,
                    revision=self.reference.tokenizer_revision,
                ),
                reference_id=self.reference.reference_id,
                reference_revision=self.reference.reference_revision,
                canonical_framework=self.reference.canonical_framework,
            ),
            evaluation_schema=EvaluationSchemaRevisionSnapshot(
                document_sha256=self.evaluation_schema.document.sha256,
                schema_id=self.evaluation_schema.schema_id,
                schema_revision=self.evaluation_schema.schema_revision,
            ),
            datasets=DatasetsRevisionSnapshot(
                document_sha256=self.datasets.document.sha256,
                entries=tuple(entries),
            ),
        )
        try:
            value.validate()
        except Exception as exc:
            raise RevisionError(str(exc)) from exc
        return value

    def to_dict(self) -> dict[str, Any]:
        return self.snapshot().to_dict()


class RevisionLoader:
    REFERENCE_FILE = "reference.json"
    EVALUATION_SCHEMA_FILE = "evaluation-schema.json"
    DATASETS_LOCK_FILE = "datasets-lock.json"
    RUNTIME_FILE = "runtime.json"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def load(self) -> RevisionBundle:
        reference_document = RevisionDocument.load(name=self.REFERENCE_FILE, path=self.root / self.REFERENCE_FILE)
        evaluation_document = RevisionDocument.load(
            name=self.EVALUATION_SCHEMA_FILE,
            path=self.root / self.EVALUATION_SCHEMA_FILE,
        )
        datasets = DatasetLock.from_document(
            RevisionDocument.load(
                name=self.DATASETS_LOCK_FILE,
                path=self.root / self.DATASETS_LOCK_FILE,
            )
        )
        runtime_path = self.root / self.RUNTIME_FILE
        if not runtime_path.is_file():
            raise RevisionError("runtime.json is required; legacy three-file config bundles are unsupported")
        try:
            catalog = load_repository_catalog(_discover_repository_root(self.root))
        except AsrCatalogError as exc:
            raise RevisionError(str(exc)) from exc
        runtime = RuntimeRevision.from_document(
            RevisionDocument.load(name=self.RUNTIME_FILE, path=runtime_path),
            catalog=catalog,
        )
        return RevisionBundle(
            reference=ReferenceRevision.from_document(reference_document),
            evaluation_schema=EvaluationSchemaRevision.from_document(evaluation_document),
            datasets=datasets,
            runtime=runtime,
            config_version=_load_config_version(self.root),
        )


def load_revision_bundle(root: str | Path) -> RevisionBundle:
    return RevisionLoader(root).load()


def _discover_repository_root(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / "config" / "asr-catalog.json").is_file():
            return parent
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        if (parent / "config" / "asr-catalog.json").is_file():
            return parent
    raise RevisionError("could not locate repository config/asr-catalog.json")
