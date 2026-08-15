"""
HF Bucket revision-lock loader.

The project keeps mutable development artifacts in a Hugging Face Bucket,
while the files below describe the immutable identities that a particular
evaluation run must consume:

    config/revisions/reference.json
    config/revisions/evaluation-schema.json
    config/revisions/datasets-lock.json

This module intentionally does not depend on the Hugging Face Python API.

GitHub Actions / local tooling may download these files using:

    hf buckets cp ...

and then point RevisionLoader at the resulting local directory.

This separation makes revision parsing usable from:

- local development
- GitHub Actions
- Docker/WSL2
- future Rust-compatible workflows
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


class RevisionError(RuntimeError):
    """Raised when revision metadata is missing or invalid."""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RevisionError(
            f"Revision file does not exist: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            value = json.load(file)

    except json.JSONDecodeError as exc:
        raise RevisionError(
            f"Invalid JSON in revision file {path}: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise RevisionError(
            f"Revision file root must be a JSON object: {path}"
        )

    return value


def _canonical_json_bytes(
    value: Mapping[str, Any],
) -> bytes:
    """
    Serialize JSON deterministically for identity hashing.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def _optional_string(
    source: Mapping[str, Any],
    key: str,
) -> str | None:
    value = source.get(key)

    if value is None:
        return None

    if not isinstance(value, str):
        raise RevisionError(
            f"{key!r} must be a string when present."
        )

    return value


@dataclass(frozen=True, slots=True)
class RevisionDocument:
    """
    Generic immutable revision document.
    """

    name: str
    path: Path
    raw: dict[str, Any]
    sha256: str

    @classmethod
    def load(
        cls,
        *,
        name: str,
        path: Path,
    ) -> "RevisionDocument":
        raw = _load_json(path)

        digest = _sha256_bytes(
            _canonical_json_bytes(raw)
        )

        return cls(
            name=name,
            path=path,
            raw=raw,
            sha256=digest,
        )


@dataclass(frozen=True, slots=True)
class ReferenceRevision:
    """
    Parsed reference.json.

    The loader intentionally supports both a minimal flat document and
    nested metadata. The exact project schema may evolve while the core
    identity fields remain stable.
    """

    document: RevisionDocument

    model_id: str
    model_revision: str

    reference_id: str | None
    reference_revision: str | None

    tokenizer_revision: str | None

    @classmethod
    def from_document(
        cls,
        document: RevisionDocument,
    ) -> "ReferenceRevision":
        raw = document.raw

        model = raw.get("model")

        if isinstance(model, dict):
            model_id = _require_string(
                model,
                "repo_id",
                document=document.name,
            )

            model_revision = _require_string(
                model,
                "revision",
                document=document.name,
            )

            tokenizer_revision = _optional_string(
                model,
                "tokenizer_revision",
            )

        else:
            model_id = _require_string(
                raw,
                "model_id",
                document=document.name,
            )

            model_revision = _require_string(
                raw,
                "model_revision",
                document=document.name,
            )

            tokenizer_revision = _optional_string(
                raw,
                "tokenizer_revision",
            )

        reference = raw.get("reference")

        if isinstance(reference, dict):
            reference_id = _optional_string(
                reference,
                "id",
            )

            reference_revision = _optional_string(
                reference,
                "revision",
            )

        else:
            reference_id = _optional_string(
                raw,
                "reference_id",
            )

            reference_revision = _optional_string(
                raw,
                "reference_revision",
            )

        return cls(
            document=document,
            model_id=model_id,
            model_revision=model_revision,
            reference_id=reference_id,
            reference_revision=reference_revision,
            tokenizer_revision=tokenizer_revision,
        )


@dataclass(frozen=True, slots=True)
class EvaluationSchemaRevision:
    """
    Parsed evaluation-schema.json revision metadata.
    """

    document: RevisionDocument

    schema_id: str
    schema_revision: str

    @classmethod
    def from_document(
        cls,
        document: RevisionDocument,
    ) -> "EvaluationSchemaRevision":
        raw = document.raw

        schema = raw.get("schema")

        if isinstance(schema, dict):
            schema_id = _require_string(
                schema,
                "id",
                document=document.name,
            )

            schema_revision = _require_string(
                schema,
                "revision",
                document=document.name,
            )

        else:
            schema_id = _require_string(
                raw,
                "schema_id",
                document=document.name,
            )

            schema_revision = _require_string(
                raw,
                "schema_revision",
                document=document.name,
            )

        return cls(
            document=document,
            schema_id=schema_id,
            schema_revision=schema_revision,
        )


@dataclass(frozen=True, slots=True)
class DatasetLockEntry:
    """
    One locked evaluation dataset.
    """

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
    """
    Parsed datasets-lock.json.
    """

    document: RevisionDocument
    datasets: tuple[DatasetLockEntry, ...]

    @classmethod
    def from_document(
        cls,
        document: RevisionDocument,
    ) -> "DatasetLock":
        raw = document.raw

        raw_datasets = raw.get("datasets")

        if not isinstance(raw_datasets, list):
            raise RevisionError(
                f"{document.name}: "
                "'datasets' must be a JSON array."
            )

        entries: list[DatasetLockEntry] = []

        for index, item in enumerate(raw_datasets):
            if not isinstance(item, dict):
                raise RevisionError(
                    f"{document.name}: datasets[{index}] "
                    "must be an object."
                )

            dataset_id = _require_string(
                item,
                "id",
                document=document.name,
            )

            repo_id = _require_string(
                item,
                "repo_id",
                document=document.name,
            )

            revision = _require_string(
                item,
                "revision",
                document=document.name,
            )

            entries.append(
                DatasetLockEntry(
                    id=dataset_id,
                    repo_id=repo_id,
                    revision=revision,
                    subset=_optional_string(
                        item,
                        "subset",
                    ),
                    split=_optional_string(
                        item,
                        "split",
                    ),
                    sha256=_optional_string(
                        item,
                        "sha256",
                    ),
                    manifest=_optional_string(
                        item,
                        "manifest",
                    ),
                    raw=dict(item),
                )
            )

        ids = [entry.id for entry in entries]

        if len(ids) != len(set(ids)):
            raise RevisionError(
                f"{document.name}: duplicate dataset IDs are not allowed."
            )

        return cls(
            document=document,
            datasets=tuple(entries),
        )

    def get(
        self,
        dataset_id: str,
    ) -> DatasetLockEntry:
        for entry in self.datasets:
            if entry.id == dataset_id:
                return entry

        raise RevisionError(
            f"Dataset is not present in datasets-lock.json: "
            f"{dataset_id}"
        )


@dataclass(frozen=True, slots=True)
class RevisionBundle:
    """
    Complete revision identity for one evaluation run.
    """

    reference: ReferenceRevision
    evaluation_schema: EvaluationSchemaRevision
    datasets: DatasetLock

    @property
    def sha256(self) -> str:
        """
        Stable combined identity for all three revision documents.
        """

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
                "document_sha256": (
                    self.reference.document.sha256
                ),
                "model_id": self.reference.model_id,
                "model_revision": (
                    self.reference.model_revision
                ),
                "reference_id": (
                    self.reference.reference_id
                ),
                "reference_revision": (
                    self.reference.reference_revision
                ),
                "tokenizer_revision": (
                    self.reference.tokenizer_revision
                ),
            },
            "evaluation_schema": {
                "document_sha256": (
                    self.evaluation_schema.document.sha256
                ),
                "schema_id": (
                    self.evaluation_schema.schema_id
                ),
                "schema_revision": (
                    self.evaluation_schema.schema_revision
                ),
            },
            "datasets": {
                "document_sha256": (
                    self.datasets.document.sha256
                ),
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
    """
    Load the three canonical revision files from a local directory.

    Expected layout:

        <root>/
        ├── reference.json
        ├── evaluation-schema.json
        └── datasets-lock.json

    GitHub Actions currently downloads HF Bucket revision files into:

        .ci/hf/config/revisions/
    """

    REFERENCE_FILE = "reference.json"
    EVALUATION_SCHEMA_FILE = "evaluation-schema.json"
    DATASETS_LOCK_FILE = "datasets-lock.json"

    def __init__(
        self,
        root: str | Path,
    ) -> None:
        self.root = Path(root).expanduser().resolve()

    def load(self) -> RevisionBundle:
        reference_document = RevisionDocument.load(
            name=self.REFERENCE_FILE,
            path=self.root / self.REFERENCE_FILE,
        )

        schema_document = RevisionDocument.load(
            name=self.EVALUATION_SCHEMA_FILE,
            path=self.root / self.EVALUATION_SCHEMA_FILE,
        )

        datasets_document = RevisionDocument.load(
            name=self.DATASETS_LOCK_FILE,
            path=self.root / self.DATASETS_LOCK_FILE,
        )

        return RevisionBundle(
            reference=ReferenceRevision.from_document(
                reference_document
            ),
            evaluation_schema=(
                EvaluationSchemaRevision.from_document(
                    schema_document
                )
            ),
            datasets=DatasetLock.from_document(
                datasets_document
            ),
        )


def load_revision_bundle(
    root: str | Path,
) -> RevisionBundle:
    """
    Convenience API.
    """

    return RevisionLoader(root).load()
