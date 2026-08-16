"""Framework-neutral Hugging Face revision-lock loading."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from parakeet_onnx.config.catalog import AsrCatalog, AsrCatalogError, load_repository_catalog


class RevisionError(RuntimeError):
    """Raised when revision metadata is missing, invalid, or incompatible."""


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
        raise RevisionError(
            f"{path.name}: schema_version must equal 1; got {value.get('schema_version')!r}"
        )
    return value


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _load_config_version(root: Path) -> str | None:
    path = root.parent / "resolved.json"
    if not path.is_file():
        return None
    value = _load_json(path)
    config_version = value.get("config_version")
    if not isinstance(config_version, str) or re.fullmatch(
        r"config-\d{6}", config_version
    ) is None:
        raise RevisionError(
            f"{path.name}: config_version must match config-NNNNNN; got {config_version!r}"
        )
    return config_version


def _reject_keys(
    source: Mapping[str, Any], keys: tuple[str, ...], *, document: str
) -> None:
    present = [key for key in keys if key in source]
    if present:
        raise RevisionError(
            f"{document}: unsupported legacy fields are present: {present!r}."
        )


def _require_mapping(
    source: Mapping[str, Any], key: str, *, document: str
) -> Mapping[str, Any]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise RevisionError(f"{document}: {key!r} must be an object.")
    return value


def _require_string(
    source: Mapping[str, Any], key: str, *, document: str
) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise RevisionError(f"{document}: {key!r} must be a non-empty string.")
    return value


def _optional_string(source: Mapping[str, Any], key: str) -> str | None:
    value = source.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RevisionError(f"{key!r} must be a non-empty string when present.")
    return value


def _require_identity(
    raw: Mapping[str, Any], key: str, *, document: str
) -> tuple[str, str]:
    value = _require_mapping(raw, key, document=document)
    return (
        _require_string(value, "repo_id", document=f"{document}.{key}"),
        _require_string(value, "revision", document=f"{document}.{key}"),
    )


@dataclass(frozen=True, slots=True)
class DecoderRevisionSet:
    supported: tuple[str, ...]
    default: str

    def validate(self, *, document: str) -> None:
        if self.default not in self.supported:
            raise RevisionError(
                f"{document}: default decoder {self.default!r} is not present in "
                f"supported={list(self.supported)!r}."
            )

    def to_dict(self) -> dict[str, Any]:
        return {"supported": list(self.supported), "default": self.default}


def _parse_legacy_decoders(
    raw: Mapping[str, Any], *, document: str
) -> DecoderRevisionSet | None:
    _reject_keys(raw, ("decoder", "decorders"), document=document)
    value = raw.get("decoders")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise RevisionError(f"{document}: 'decoders' must be an object")
    supported_raw = value.get("supported")
    if not isinstance(supported_raw, list) or not supported_raw or not all(
        isinstance(item, str) and item for item in supported_raw
    ):
        raise RevisionError(f"{document}: decoders.supported must be a string array")
    default = value.get("default")
    if not isinstance(default, str) or not default:
        raise RevisionError(f"{document}: decoders.default must be a string")
    result = DecoderRevisionSet(tuple(supported_raw), default)
    result.validate(document=document)
    return result


@dataclass(frozen=True, slots=True)
class RevisionDocument:
    name: str
    path: Path
    raw: dict[str, Any]
    sha256: str

    @classmethod
    def load(cls, *, name: str, path: Path) -> "RevisionDocument":
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
    decoders: DecoderRevisionSet

    @classmethod
    def from_document(
        cls, document: RevisionDocument, *, catalog: AsrCatalog
    ) -> "RuntimeRevision":
        raw = document.raw
        catalog_raw = _require_mapping(raw, "catalog", document=document.name)
        catalog_id = _require_string(
            catalog_raw, "id", document=f"{document.name}.catalog"
        )
        catalog_sha = _require_string(
            catalog_raw, "sha256", document=f"{document.name}.catalog"
        )
        if catalog_id != catalog.catalog_id:
            raise RevisionError(
                f"runtime.json catalog id mismatch: lock={catalog_id!r}, "
                f"repository={catalog.catalog_id!r}"
            )
        if catalog_sha.lower() != catalog.sha256.lower():
            raise RevisionError(
                "runtime.json catalog SHA-256 does not match the checked-out "
                "config/asr-catalog.json; reproduce this config with the Git commit "
                "that contains the locked catalog snapshot"
            )
        profile_set_id = _require_string(raw, "profile_set", document=document.name)
        try:
            profile_set = catalog.profile_set(profile_set_id)
        except AsrCatalogError as exc:
            raise RevisionError(str(exc)) from exc
        variants = dict(profile_set.variants)
        supported_decoders = tuple(
            dict.fromkeys(
                catalog.decoder_profile(profile_id).decoder
                for profile_id in variants.values()
            )
        )
        default_profile = profile_set.profile_id_for()
        default_decoder = catalog.decoder_profile(default_profile).decoder
        decoders = DecoderRevisionSet(supported_decoders, default_decoder)
        decoders.validate(document=document.name)
        return cls(
            document=document,
            catalog_id=catalog_id,
            catalog_sha256=catalog_sha,
            profile_set_id=profile_set_id,
            variants=variants,
            default_variant=profile_set.default_variant,
            decoders=decoders,
        )

    def resolve_variant(
        self, variant: str | None, *, catalog: AsrCatalog
    ) -> tuple[str, str, str]:
        selected = variant or self.default_variant
        try:
            profile_id = self.variants[selected]
        except KeyError as exc:
            raise RevisionError(
                f"unknown runtime variant {selected!r}; available={sorted(self.variants)}"
            ) from exc
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
    decoders: DecoderRevisionSet

    @classmethod
    def from_document(
        cls, document: RevisionDocument, *, decoders: DecoderRevisionSet
    ) -> "ReferenceRevision":
        raw = document.raw
        _reject_keys(
            raw,
            (
                "model",
                "model_id",
                "model_revision",
                "tokenizer_revision",
                "reference_id",
                "reference_revision",
                "canonical_framework",
            ),
            document=document.name,
        )
        development_repo_id, development_revision = _require_identity(
            raw, "development_artifact", document=document.name
        )
        upstream_repo_id, upstream_revision = _require_identity(
            raw, "upstream", document=document.name
        )
        tokenizer_repo_id, tokenizer_revision = _require_identity(
            raw, "tokenizer", document=document.name
        )
        reference = _require_mapping(raw, "reference", document=document.name)
        return cls(
            document=document,
            development_artifact_repo_id=development_repo_id,
            development_artifact_revision=development_revision,
            upstream_repo_id=upstream_repo_id,
            upstream_revision=upstream_revision,
            tokenizer_repo_id=tokenizer_repo_id,
            tokenizer_revision=tokenizer_revision,
            reference_id=_require_string(
                reference, "id", document=f"{document.name}.reference"
            ),
            reference_revision=_require_string(
                reference, "revision", document=f"{document.name}.reference"
            ),
            canonical_framework=_require_string(
                reference,
                "canonical_framework",
                document=f"{document.name}.reference",
            ),
            decoders=decoders,
        )


@dataclass(frozen=True, slots=True)
class EvaluationSchemaRevision:
    document: RevisionDocument
    schema_id: str
    schema_revision: str
    decoders: DecoderRevisionSet

    @classmethod
    def from_document(
        cls, document: RevisionDocument, *, decoders: DecoderRevisionSet
    ) -> "EvaluationSchemaRevision":
        raw = document.raw
        _reject_keys(raw, ("schema_id", "schema_revision"), document=document.name)
        schema = _require_mapping(raw, "schema", document=document.name)
        return cls(
            document=document,
            schema_id=_require_string(
                schema, "id", document=f"{document.name}.schema"
            ),
            schema_revision=_require_string(
                schema, "revision", document=f"{document.name}.schema"
            ),
            decoders=decoders,
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
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DatasetLock:
    document: RevisionDocument
    datasets: tuple[DatasetLockEntry, ...]

    @classmethod
    def from_document(cls, document: RevisionDocument) -> "DatasetLock":
        raw_datasets = document.raw.get("datasets")
        if not isinstance(raw_datasets, list):
            raise RevisionError(f"{document.name}: 'datasets' must be a JSON array.")
        entries: list[DatasetLockEntry] = []
        for index, item in enumerate(raw_datasets):
            if not isinstance(item, dict):
                raise RevisionError(
                    f"{document.name}: datasets[{index}] must be an object."
                )
            entries.append(
                DatasetLockEntry(
                    id=_require_string(item, "id", document=document.name),
                    repo_id=_require_string(item, "repo_id", document=document.name),
                    revision=_require_string(item, "revision", document=document.name),
                    subset=_optional_string(item, "subset"),
                    split=_optional_string(item, "split"),
                    sha256=_optional_string(item, "sha256"),
                    manifest=_optional_string(item, "manifest"),
                    raw=dict(item),
                )
            )
        ids = [entry.id for entry in entries]
        if len(ids) != len(set(ids)):
            raise RevisionError(
                f"{document.name}: duplicate dataset IDs are not allowed."
            )
        return cls(document=document, datasets=tuple(entries))

    def get(self, dataset_id: str) -> DatasetLockEntry:
        for entry in self.datasets:
            if entry.id == dataset_id:
                return entry
        raise RevisionError(
            f"Dataset is not present in datasets-lock.json: {dataset_id}"
        )


@dataclass(frozen=True, slots=True)
class RevisionBundle:
    reference: ReferenceRevision
    evaluation_schema: EvaluationSchemaRevision
    datasets: DatasetLock
    runtime: RuntimeRevision | None
    config_version: str | None = None

    @property
    def sha256(self) -> str:
        digest = hashlib.sha256()
        documents = [
            self.reference.document,
            self.evaluation_schema.document,
            self.datasets.document,
        ]
        if self.runtime is not None:
            documents.append(self.runtime.document)
        for document in documents:
            digest.update(document.sha256.encode("ascii"))
        return digest.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        reference = self.reference
        runtime_dict: dict[str, Any] | None = None
        if self.runtime is not None:
            runtime_dict = {
                "document_sha256": self.runtime.document.sha256,
                "catalog": {
                    "id": self.runtime.catalog_id,
                    "sha256": self.runtime.catalog_sha256,
                },
                "profile_set": self.runtime.profile_set_id,
                "variants": dict(self.runtime.variants),
                "default_variant": self.runtime.default_variant,
                "decoders": self.runtime.decoders.to_dict(),
            }
        return {
            "config_version": self.config_version,
            "bundle_sha256": self.sha256,
            "runtime": runtime_dict,
            "reference": {
                "document_sha256": reference.document.sha256,
                "development_artifact": {
                    "repo_id": reference.development_artifact_repo_id,
                    "revision": reference.development_artifact_revision,
                },
                "upstream": {
                    "repo_id": reference.upstream_repo_id,
                    "revision": reference.upstream_revision,
                },
                "tokenizer": {
                    "repo_id": reference.tokenizer_repo_id,
                    "revision": reference.tokenizer_revision,
                },
                "reference_id": reference.reference_id,
                "reference_revision": reference.reference_revision,
                "canonical_framework": reference.canonical_framework,
                "decoders": reference.decoders.to_dict(),
            },
            "evaluation_schema": {
                "document_sha256": self.evaluation_schema.document.sha256,
                "schema_id": self.evaluation_schema.schema_id,
                "schema_revision": self.evaluation_schema.schema_revision,
                "decoders": self.evaluation_schema.decoders.to_dict(),
            },
            "datasets": {
                "document_sha256": self.datasets.document.sha256,
                "entries": [
                    {
                        "id": entry.id,
                        "repo_id": entry.repo_id,
                        "revision": entry.revision,
                        "subset": entry.subset,
                        "split": entry.split,
                        "sha256": entry.sha256,
                        "manifest": entry.manifest,
                    }
                    for entry in self.datasets.datasets
                ],
            },
        }


class RevisionLoader:
    REFERENCE_FILE = "reference.json"
    EVALUATION_SCHEMA_FILE = "evaluation-schema.json"
    DATASETS_LOCK_FILE = "datasets-lock.json"
    RUNTIME_FILE = "runtime.json"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def load(self) -> RevisionBundle:
        reference_document = RevisionDocument.load(
            name=self.REFERENCE_FILE, path=self.root / self.REFERENCE_FILE
        )
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
        runtime: RuntimeRevision | None = None
        if runtime_path.is_file():
            try:
                catalog = load_repository_catalog(_discover_repository_root(self.root))
            except AsrCatalogError as exc:
                raise RevisionError(str(exc)) from exc
            runtime = RuntimeRevision.from_document(
                RevisionDocument.load(name=self.RUNTIME_FILE, path=runtime_path),
                catalog=catalog,
            )
            decoders = runtime.decoders
            if "decoders" in reference_document.raw or "decoders" in evaluation_document.raw:
                raise RevisionError(
                    "runtime.json is present, so reference.json and "
                    "evaluation-schema.json must not repeat decoder declarations"
                )
        else:
            reference_decoders = _parse_legacy_decoders(
                reference_document.raw, document=reference_document.name
            )
            evaluation_decoders = _parse_legacy_decoders(
                evaluation_document.raw, document=evaluation_document.name
            )
            if reference_decoders is None or evaluation_decoders is None:
                raise RevisionError(
                    "runtime.json is required for the normalized config contract; "
                    "legacy configs must keep decoders in both reference/evaluation documents"
                )
            if set(reference_decoders.supported) - set(evaluation_decoders.supported):
                raise RevisionError(
                    "legacy evaluation-schema.json does not support all reference decoders"
                )
            if reference_decoders.default not in evaluation_decoders.supported:
                raise RevisionError(
                    "legacy evaluation-schema.json does not support the reference default decoder"
                )
            decoders = reference_decoders

        return RevisionBundle(
            reference=ReferenceRevision.from_document(
                reference_document, decoders=decoders
            ),
            evaluation_schema=EvaluationSchemaRevision.from_document(
                evaluation_document, decoders=decoders
            ),
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
