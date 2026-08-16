"""Framework-neutral Hugging Face revision-lock loading."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class RevisionError(RuntimeError):
    """Raised when revision metadata is missing, invalid, or incompatible."""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RevisionError(f"Revision file does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except json.JSONDecodeError as exc:
        raise RevisionError(f"Invalid JSON in revision file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RevisionError(f"Revision file root must be a JSON object: {path}")
    if value.get("schema_version") != 1:
        raise RevisionError(
            f"{path.name}: schema_version must equal 1; "
            f"got {value.get('schema_version')!r}"
        )
    return value


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reject_keys(
    source: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    document: str,
) -> None:
    present = [key for key in keys if key in source]
    if present:
        raise RevisionError(
            f"{document}: unsupported legacy fields are present: {present!r}. "
            "Rewrite the document using the canonical revision contract."
        )


def _require_mapping(
    source: Mapping[str, Any],
    key: str,
    *,
    document: str,
) -> Mapping[str, Any]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise RevisionError(f"{document}: {key!r} must be an object.")
    return value


def _require_string(
    source: Mapping[str, Any],
    key: str,
    *,
    document: str,
) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise RevisionError(
            f"{document}: {key!r} must be a non-empty string."
        )
    return value


def _optional_string(source: Mapping[str, Any], key: str) -> str | None:
    value = source.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RevisionError(f"{key!r} must be a non-empty string when present.")
    return value


def _require_identity(
    raw: Mapping[str, Any],
    key: str,
    *,
    document: str,
) -> tuple[str, str]:
    value = _require_mapping(raw, key, document=document)
    return (
        _require_string(value, "repo_id", document=f"{document}.{key}"),
        _require_string(value, "revision", document=f"{document}.{key}"),
    )


def _decoder_id(value: Any, *, document: str, field: str) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, Mapping):
        for key in ("id", "name", "type", "decoder"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
    raise RevisionError(
        f"{document}: {field} must be a decoder ID string or an object "
        "containing one of: id, name, type, decoder."
    )


def _decoder_list(
    source: Mapping[str, Any],
    key: str,
    *,
    document: str,
) -> tuple[str, ...]:
    value = source.get(key)
    if not isinstance(value, list) or not value:
        raise RevisionError(
            f"{document}: {key!r} must be a non-empty array."
        )
    result = tuple(
        _decoder_id(item, document=document, field=f"{key}[{index}]")
        for index, item in enumerate(value)
    )
    if len(result) != len(set(result)):
        raise RevisionError(f"{document}: {key!r} must not contain duplicates.")
    return result


@dataclass(frozen=True, slots=True)
class DecoderRevisionSet:
    supported: tuple[str, ...]
    default: str

    def validate(self, *, document: str) -> None:
        if self.default not in self.supported:
            raise RevisionError(
                f"{document}: default decoder {self.default!r} is not present "
                f"in decoders.supported={list(self.supported)!r}."
            )

    def to_dict(self) -> dict[str, Any]:
        return {"supported": list(self.supported), "default": self.default}


def _parse_decoders(
    raw: Mapping[str, Any],
    *,
    document: str,
) -> DecoderRevisionSet:
    _reject_keys(raw, ("decoder", "decorders"), document=document)
    value = _require_mapping(raw, "decoders", document=document)
    supported = _decoder_list(value, "supported", document=document)
    default = _decoder_id(
        value.get("default"),
        document=document,
        field="decoders.default",
    )
    result = DecoderRevisionSet(supported=supported, default=default)
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
    def from_document(cls, document: RevisionDocument) -> "ReferenceRevision":
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
            raw,
            "development_artifact",
            document=document.name,
        )
        upstream_repo_id, upstream_revision = _require_identity(
            raw,
            "upstream",
            document=document.name,
        )
        tokenizer_repo_id, tokenizer_revision = _require_identity(
            raw,
            "tokenizer",
            document=document.name,
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
                reference,
                "id",
                document=f"{document.name}.reference",
            ),
            reference_revision=_require_string(
                reference,
                "revision",
                document=f"{document.name}.reference",
            ),
            canonical_framework=_require_string(
                reference,
                "canonical_framework",
                document=f"{document.name}.reference",
            ),
            decoders=_parse_decoders(raw, document=document.name),
        )


@dataclass(frozen=True, slots=True)
class EvaluationSchemaRevision:
    document: RevisionDocument
    schema_id: str
    schema_revision: str
    decoders: DecoderRevisionSet

    @classmethod
    def from_document(
        cls,
        document: RevisionDocument,
    ) -> "EvaluationSchemaRevision":
        raw = document.raw
        _reject_keys(
            raw,
            ("schema_id", "schema_revision"),
            document=document.name,
        )
        schema = _require_mapping(raw, "schema", document=document.name)
        return cls(
            document=document,
            schema_id=_require_string(
                schema,
                "id",
                document=f"{document.name}.schema",
            ),
            schema_revision=_require_string(
                schema,
                "revision",
                document=f"{document.name}.schema",
            ),
            decoders=_parse_decoders(raw, document=document.name),
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
            raise RevisionError(
                f"{document.name}: 'datasets' must be a JSON array."
            )

        entries: list[DatasetLockEntry] = []
        for index, item in enumerate(raw_datasets):
            if not isinstance(item, dict):
                raise RevisionError(
                    f"{document.name}: datasets[{index}] must be an object."
                )
            entries.append(
                DatasetLockEntry(
                    id=_require_string(item, "id", document=document.name),
                    repo_id=_require_string(
                        item,
                        "repo_id",
                        document=document.name,
                    ),
                    revision=_require_string(
                        item,
                        "revision",
                        document=document.name,
                    ),
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

    def validate_compatibility(self) -> None:
        reference_decoders = set(self.reference.decoders.supported)
        schema_decoders = set(self.evaluation_schema.decoders.supported)
        unsupported = reference_decoders - schema_decoders
        if unsupported:
            raise RevisionError(
                "evaluation-schema.json does not support all reference "
                f"decoders: {sorted(unsupported)!r}"
            )
        default = self.reference.decoders.default
        if default not in schema_decoders:
            raise RevisionError(
                "evaluation-schema.json does not support the reference "
                f"default decoder: {default!r}"
            )

    @property
    def sha256(self) -> str:
        digest = hashlib.sha256()
        for value in (
            self.reference.document.sha256,
            self.evaluation_schema.document.sha256,
            self.datasets.document.sha256,
        ):
            digest.update(value.encode("ascii"))
        return digest.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        reference = self.reference
        return {
            "bundle_sha256": self.sha256,
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

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def load(self) -> RevisionBundle:
        bundle = RevisionBundle(
            reference=ReferenceRevision.from_document(
                RevisionDocument.load(
                    name=self.REFERENCE_FILE,
                    path=self.root / self.REFERENCE_FILE,
                )
            ),
            evaluation_schema=EvaluationSchemaRevision.from_document(
                RevisionDocument.load(
                    name=self.EVALUATION_SCHEMA_FILE,
                    path=self.root / self.EVALUATION_SCHEMA_FILE,
                )
            ),
            datasets=DatasetLock.from_document(
                RevisionDocument.load(
                    name=self.DATASETS_LOCK_FILE,
                    path=self.root / self.DATASETS_LOCK_FILE,
                )
            ),
        )
        bundle.validate_compatibility()
        return bundle


def load_revision_bundle(root: str | Path) -> RevisionBundle:
    return RevisionLoader(root).load()
