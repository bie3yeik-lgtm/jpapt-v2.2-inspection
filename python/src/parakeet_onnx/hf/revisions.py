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


def _decoder_id(
    value: Any,
    *,
    document: str,
    field: str,
) -> str:
    """Normalize a string or structured decoder declaration to one ID."""

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
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RevisionError(f"{document}: {key!r} must be an array when present.")
    result = tuple(
        _decoder_id(
            item,
            document=document,
            field=f"{key}[{index}]",
        )
        for index, item in enumerate(value)
    )
    if len(result) != len(set(result)):
        raise RevisionError(f"{document}: {key!r} must not contain duplicates.")
    return result


@dataclass(frozen=True, slots=True)
class DecoderRevisionSet:
    """Framework-neutral decoder capability declaration."""

    supported: tuple[str, ...]
    default: str | None

    def validate(self, *, document: str) -> None:
        if self.default is not None and self.default not in self.supported:
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
    """Parse decoder capability metadata without assuming one framework.

    Accepted forms include string IDs and structured objects such as
    ``{"id": "ctc", ...}``.  ``decorders`` is accepted as a legacy typo but
    normalized output always uses ``decoders``.
    """

    value = raw.get("decoders")
    if value is None:
        value = raw.get("decorders")
    if value is None:
        legacy = raw.get("decoder")
        if legacy is None:
            return DecoderRevisionSet((), None)
        decoder = _decoder_id(
            legacy,
            document=document,
            field="decoder",
        )
        return DecoderRevisionSet((decoder,), decoder)

    if isinstance(value, list):
        supported = _decoder_list(
            {"supported": value},
            "supported",
            document=document,
        )
        result = DecoderRevisionSet(
            supported=supported,
            default=supported[0] if len(supported) == 1 else None,
        )
        result.validate(document=document)
        return result

    if not isinstance(value, Mapping):
        raise RevisionError(
            f"{document}: 'decoders' must be an object or an array."
        )

    supported = _decoder_list(value, "supported", document=document)
    default_raw = value.get("default")
    default = (
        None
        if default_raw is None
        else _decoder_id(
            default_raw,
            document=document,
            field="decoders.default",
        )
    )
    if default is not None and not supported:
        supported = (default,)

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
    model_id: str
    model_revision: str
    reference_id: str | None
    reference_revision: str | None
    tokenizer_revision: str | None
    canonical_framework: str | None
    decoders: DecoderRevisionSet

    @classmethod
    def from_document(cls, document: RevisionDocument) -> "ReferenceRevision":
        raw = document.raw
        model = raw.get("model")
        if isinstance(model, Mapping):
            model_id = _require_string(model, "repo_id", document=document.name)
            model_revision = _require_string(
                model,
                "revision",
                document=document.name,
            )
            tokenizer_revision = _optional_string(model, "tokenizer_revision")
            model_framework = _optional_string(model, "framework")
        else:
            model_id = _require_string(raw, "model_id", document=document.name)
            model_revision = _require_string(
                raw,
                "model_revision",
                document=document.name,
            )
            tokenizer_revision = _optional_string(raw, "tokenizer_revision")
            model_framework = None

        reference = raw.get("reference")
        if isinstance(reference, Mapping):
            reference_id = _optional_string(reference, "id")
            reference_revision = _optional_string(reference, "revision")
            reference_framework = _optional_string(
                reference,
                "canonical_framework",
            )
        else:
            reference_id = _optional_string(raw, "reference_id")
            reference_revision = _optional_string(raw, "reference_revision")
            reference_framework = None

        return cls(
            document=document,
            model_id=model_id,
            model_revision=model_revision,
            reference_id=reference_id,
            reference_revision=reference_revision,
            tokenizer_revision=tokenizer_revision,
            canonical_framework=(
                reference_framework
                or model_framework
                or _optional_string(raw, "canonical_framework")
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
        schema = raw.get("schema")
        if isinstance(schema, Mapping):
            schema_id = _require_string(schema, "id", document=document.name)
            schema_revision = _require_string(
                schema,
                "revision",
                document=document.name,
            )
        else:
            schema_id = _require_string(raw, "schema_id", document=document.name)
            schema_revision = _require_string(
                raw,
                "schema_revision",
                document=document.name,
            )
        return cls(
            document=document,
            schema_id=schema_id,
            schema_revision=schema_revision,
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
        if reference_decoders and schema_decoders:
            unsupported = reference_decoders - schema_decoders
            if unsupported:
                raise RevisionError(
                    "evaluation-schema.json does not support all reference "
                    f"decoders: {sorted(unsupported)!r}"
                )
        default = self.reference.decoders.default
        if default is not None and schema_decoders and default not in schema_decoders:
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
        return {
            "bundle_sha256": self.sha256,
            "reference": {
                "document_sha256": self.reference.document.sha256,
                "model_id": self.reference.model_id,
                "model_revision": self.reference.model_revision,
                "reference_id": self.reference.reference_id,
                "reference_revision": self.reference.reference_revision,
                "tokenizer_revision": self.reference.tokenizer_revision,
                "canonical_framework": self.reference.canonical_framework,
                "decoders": self.reference.decoders.to_dict(),
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
