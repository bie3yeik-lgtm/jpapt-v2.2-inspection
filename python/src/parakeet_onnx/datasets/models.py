from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Literal


SelectionStrategy = Literal["stable_hash"]


class JsonModelMixin:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class ManifestSelection(JsonModelMixin):
    count: int
    seed: str
    strategy: SelectionStrategy = "stable_hash"

    def validate(self) -> None:
        if self.strategy != "stable_hash":
            raise ValueError(f"Unsupported selection strategy: {self.strategy}")
        if self.count <= 0:
            raise ValueError("Manifest selection count must be positive.")
        if not self.seed:
            raise ValueError("Manifest selection seed must not be empty.")


@dataclass(frozen=True, slots=True)
class ManifestFilters(JsonModelMixin):
    min_duration_sec: float | None = None
    max_duration_sec: float | None = None

    def validate(self) -> None:
        if self.min_duration_sec is not None and self.min_duration_sec < 0:
            raise ValueError("min_duration_sec must be >= 0 when present.")
        if self.max_duration_sec is not None and self.max_duration_sec <= 0:
            raise ValueError("max_duration_sec must be > 0 when present.")
        if (
            self.min_duration_sec is not None
            and self.max_duration_sec is not None
            and self.max_duration_sec <= self.min_duration_sec
        ):
            raise ValueError(
                "max_duration_sec must be greater than min_duration_sec."
            )

    def accepts(self, duration_sec: float) -> bool:
        if self.min_duration_sec is not None and duration_sec < self.min_duration_sec:
            return False
        if self.max_duration_sec is not None and duration_sec >= self.max_duration_sec:
            return False
        return True


@dataclass(frozen=True, slots=True)
class ManifestEntry(JsonModelMixin):
    id: str
    dataset_id: str
    selection: ManifestSelection
    filters: ManifestFilters
    tags: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Manifest entry id must not be empty.")
        if not self.dataset_id:
            raise ValueError("Manifest dataset_id must not be empty.")
        self.selection.validate()
        self.filters.validate()


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    identity: str
    index: int
    duration_sec: float
    sample_rate_hz: int | None
    transcription: str
    audio: Any
    source_id: str | None = None
    audio_path: str | None = None
    metadata: dict[str, Any] | None = None

    def validate(self) -> None:
        if not self.identity:
            raise ValueError("DatasetRecord.identity must not be empty.")
        if self.index < 0:
            raise ValueError("DatasetRecord.index must be >= 0.")
        if self.duration_sec < 0:
            raise ValueError("DatasetRecord.duration_sec must be >= 0.")
        if self.sample_rate_hz is not None and self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive when present.")


@dataclass(frozen=True, slots=True)
class ResolvedDatasetSample(JsonModelMixin):
    id: str
    manifest_entry_id: str
    dataset_id: str
    dataset_repo_id: str
    dataset_revision: str
    subset: str | None
    split: str | None
    row_index: int
    source_identity: str
    selection_hash: str
    selection_rank: int
    duration_sec: float
    sample_rate_hz: int | None
    transcription: str
    tags: tuple[str, ...]
    audio_path: str | None = None
    audio_sha256: str | None = None

    def logical_identity(self) -> str:
        return (
            f"{self.dataset_id}:"
            f"{self.dataset_revision}:"
            f"{self.source_identity}"
        )


@dataclass(frozen=True, slots=True)
class ResolvedManifest(JsonModelMixin):
    schema_version: int
    manifest_path: str
    expected_sample_count: int
    resolved_sample_count: int
    samples: tuple[ResolvedDatasetSample, ...]

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                f"Unsupported resolved manifest schema: {self.schema_version}"
            )
        if self.resolved_sample_count != len(self.samples):
            raise ValueError("resolved_sample_count does not match samples.")
        if self.resolved_sample_count != self.expected_sample_count:
            raise ValueError("Resolved sample count does not match expected sample count.")
        ids = [sample.id for sample in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("Resolved manifest contains duplicate sample IDs.")

    def write_json(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_json(indent=2) + "\n", encoding="utf-8")
