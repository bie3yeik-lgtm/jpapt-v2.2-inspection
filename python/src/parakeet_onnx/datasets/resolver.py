"""
Deterministic dataset resolver.

Resolution flow:

    manifest entry
        ↓
    datasets-lock.json entry
        ↓
    pinned dataset revision
        ↓
    backend-neutral DatasetRecord objects
        ↓
    duration filter
        ↓
    stable SHA-256 ordering
        ↓
    first N
        ↓
    ResolvedDatasetSample

The core resolver does not depend on Hugging Face directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
import hashlib
from pathlib import Path
from typing import Any

from parakeet_onnx.hf.revisions import (
    DatasetLock,
    DatasetLockEntry,
)

from .errors import DatasetResolutionError
from .manifest import (
    ManifestLoader,
    stable_hash,
)
from .models import (
    DatasetRecord,
    ManifestEntry,
    ResolvedDatasetSample,
    ResolvedManifest,
)


class DatasetBackend(ABC):
    """
    Backend-neutral locked dataset reader.
    """

    @abstractmethod
    def iter_records(
        self,
        lock: DatasetLockEntry,
    ) -> Iterable[DatasetRecord]:
        """
        Yield every record from exactly the pinned dataset revision.
        """


class HuggingFaceDatasetBackend(DatasetBackend):
    """
    Hugging Face datasets implementation.

    Requires the optional ``datasets`` package.

    Loading is pinned with ``revision=lock.revision``.
    """

    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        streaming: bool = False,
    ) -> None:
        self.cache_dir = (
            str(
                Path(cache_dir)
                .expanduser()
                .resolve()
            )
            if cache_dir is not None
            else None
        )

        self.streaming = streaming

    def iter_records(
        self,
        lock: DatasetLockEntry,
    ) -> Iterator[DatasetRecord]:
        try:
            from datasets import load_dataset
        except ImportError as exc:
            raise DatasetResolutionError(
                "HuggingFaceDatasetBackend requires "
                "the 'datasets' Python package."
            ) from exc

        kwargs: dict[str, Any] = {
            "path": lock.repo_id,
            "revision": lock.revision,
            "streaming": self.streaming,
        }

        if self.cache_dir is not None:
            kwargs["cache_dir"] = self.cache_dir

        if lock.subset:
            kwargs["name"] = lock.subset

        if lock.split:
            kwargs["split"] = lock.split

        try:
            dataset = load_dataset(**kwargs)
        except Exception as exc:
            raise DatasetResolutionError(
                "Failed to load locked Hugging Face dataset: "
                f"repo={lock.repo_id!r}, "
                f"revision={lock.revision!r}, "
                f"subset={lock.subset!r}, "
                f"split={lock.split!r}: {exc}"
            ) from exc

        # A locked evaluation dataset should normally resolve to one split.
        # If no split was pinned and DatasetDict is returned, fail rather
        # than selecting a split implicitly.
        if hasattr(dataset, "keys") and not hasattr(
            dataset,
            "column_names",
        ):
            raise DatasetResolutionError(
                f"Dataset {lock.id!r} resolved to multiple splits. "
                "datasets-lock.json must pin a split."
            )

        for index, row in enumerate(dataset):
            if not isinstance(row, dict):
                raise DatasetResolutionError(
                    f"Dataset row {index} is not a mapping."
                )

            yield self._convert_row(
                row=row,
                index=index,
            )

    def _convert_row(
        self,
        *,
        row: dict[str, Any],
        index: int,
    ) -> DatasetRecord:
        audio = self._find_audio(row)

        transcription = self._find_transcription(
            row
        )

        source_id = self._find_source_id(
            row
        )

        audio_path = self._audio_path(
            audio
        )

        identity = self._make_identity(
            row=row,
            source_id=source_id,
            audio_path=audio_path,
            index=index,
        )

        sample_rate = self._sample_rate(
            audio
        )

        duration = self._duration(
            row=row,
            audio=audio,
            sample_rate=sample_rate,
        )

        record = DatasetRecord(
            identity=identity,
            index=index,
            duration_sec=duration,
            sample_rate_hz=sample_rate,
            transcription=transcription,
            audio=audio,
            source_id=source_id,
            audio_path=audio_path,
            metadata=None,
        )

        try:
            record.validate()
        except ValueError as exc:
            raise DatasetResolutionError(
                f"Invalid dataset row {index}: {exc}"
            ) from exc

        return record

    @staticmethod
    def _find_audio(
        row: dict[str, Any],
    ) -> Any:
        for key in (
            "audio",
            "speech",
            "waveform",
        ):
            if key in row:
                return row[key]

        raise DatasetResolutionError(
            "Dataset row has no supported audio column. "
            "Expected one of: audio, speech, waveform."
        )

    @staticmethod
    def _find_transcription(
        row: dict[str, Any],
    ) -> str:
        for key in (
            "transcription",
            "sentence",
            "text",
            "transcript",
        ):
            value = row.get(key)

            if isinstance(value, str):
                return value

        raise DatasetResolutionError(
            "Dataset row has no supported transcription column. "
            "Expected one of: transcription, sentence, text, transcript."
        )

    @staticmethod
    def _find_source_id(
        row: dict[str, Any],
    ) -> str | None:
        for key in (
            "id",
            "utt_id",
            "utterance_id",
            "client_id",
        ):
            value = row.get(key)

            if value is not None:
                text = str(value)

                if text:
                    return text

        return None

    @staticmethod
    def _audio_path(
        audio: Any,
    ) -> str | None:
        if isinstance(audio, dict):
            value = audio.get("path")

            if value:
                return str(value)

        if isinstance(audio, str):
            return audio

        return None

    @staticmethod
    def _sample_rate(
        audio: Any,
    ) -> int | None:
        if isinstance(audio, dict):
            value = (
                audio.get("sampling_rate")
                or audio.get("sample_rate")
            )

            if value is not None:
                return int(value)

        return None

    @staticmethod
    def _duration(
        *,
        row: dict[str, Any],
        audio: Any,
        sample_rate: int | None,
    ) -> float:
        for key in (
            "duration",
            "duration_sec",
            "seconds",
        ):
            value = row.get(key)

            if value is not None:
                return float(value)

        if isinstance(audio, dict):
            array = audio.get("array")

            if (
                array is not None
                and sample_rate is not None
                and sample_rate > 0
            ):
                try:
                    return (
                        float(len(array))
                        / float(sample_rate)
                    )
                except TypeError:
                    pass

        raise DatasetResolutionError(
            "Unable to determine audio duration. "
            "Dataset must expose duration or decodable audio length."
        )

    @staticmethod
    def _make_identity(
        *,
        row: dict[str, Any],
        source_id: str | None,
        audio_path: str | None,
        index: int,
    ) -> str:
        if source_id:
            return f"id:{source_id}"

        if audio_path:
            return f"path:{audio_path}"

        # The row index is stable because datasets-lock.json pins the exact
        # dataset revision and split.
        return f"index:{index}"


class DatasetResolver:
    """
    Resolve evaluation manifests against datasets-lock.json.
    """

    def __init__(
        self,
        *,
        dataset_lock: DatasetLock,
        backend: DatasetBackend,
        materializer: DatasetMaterializer,
        repository_root: str | Path | None = None,
    ) -> None:
        self.dataset_lock = dataset_lock
        self.backend = backend
        self.materializer = materializer
        self.manifest_loader = ManifestLoader(
            repository_root=repository_root
        )

    def resolve(
        self,
        manifest_path: str | Path,
        *,
        expected_sample_count: int | None = None,
    ) -> ResolvedManifest:
        entries = self.manifest_loader.load(
            manifest_path
        )

        manifest_expected = (
            self.manifest_loader.expected_sample_count(
                entries
            )
        )

        if (
            expected_sample_count is not None
            and manifest_expected
            != expected_sample_count
        ):
            raise DatasetResolutionError(
                "Manifest requested sample count does not match "
                "evaluation configuration: "
                f"manifest={manifest_expected}, "
                f"expected={expected_sample_count}"
            )

        selected: list[
            ResolvedDatasetSample
        ] = []

        seen_logical_ids: set[str] = set()

        for entry in entries:
            lock = self.dataset_lock.get(
                entry.dataset_id
            )

            resolved = self._resolve_entry(
                entry=entry,
                lock=lock,
            )

            for sample in resolved:
                logical = sample.logical_identity()

                if logical in seen_logical_ids:
                    raise DatasetResolutionError(
                        "The same logical dataset sample was "
                        "selected by multiple manifest entries: "
                        f"{logical}"
                    )

                seen_logical_ids.add(
                    logical
                )

                selected.append(sample)

        manifest_location = str(
            Path(manifest_path).as_posix()
        )

        result = ResolvedManifest(
            schema_version=1,
            manifest_path=manifest_location,
            expected_sample_count=manifest_expected,
            resolved_sample_count=len(selected),
            samples=tuple(selected),
        )

        try:
            result.validate()
        except ValueError as exc:
            raise DatasetResolutionError(
                str(exc)
            ) from exc

        return result

    def _resolve_entry(
        self,
        *,
        entry: ManifestEntry,
        lock: DatasetLockEntry,
    ) -> list[ResolvedDatasetSample]:
        candidates: list[
            tuple[bytes, str, DatasetRecord]
        ] = []

        for record in self.backend.iter_records(
            lock
        ):
            if not entry.filters.accepts(
                record.duration_sec
            ):
                continue

            digest_hex = stable_hash(
                dataset_revision=lock.revision,
                sample_identity=record.identity,
                seed=entry.selection.seed,
            )

            digest_bytes = bytes.fromhex(
                digest_hex
            )

            candidates.append(
                (
                    digest_bytes,
                    digest_hex,
                    record,
                )
            )

        # Secondary index ordering is defensive only. SHA-256 collisions are
        # practically irrelevant, but deterministic tie handling is cheap.
        candidates.sort(
            key=lambda item: (
                item[0],
                item[2].index,
            )
        )

        count = entry.selection.count

        if len(candidates) < count:
            raise DatasetResolutionError(
                f"Manifest entry {entry.id!r} requested "
                f"{count} samples, but only {len(candidates)} "
                "records passed its filters."
            )

        selected: list[
            ResolvedDatasetSample
        ] = []

        for rank, (
            _,
            digest_hex,
            record,
        ) in enumerate(
            candidates[:count],
            start=1,
        ):
            sample_id = self._sample_id(
                entry=entry,
                record=record,
            )

	  materialized = self.materializer.materialize(
	        record=record,
	        dataset_revision=lock.revision,
	  )

            selected.append(
                ResolvedDatasetSample(
                    id=sample_id,
                    manifest_entry_id=entry.id,
                    dataset_id=lock.id,
                    dataset_repo_id=lock.repo_id,
                    dataset_revision=lock.revision,
                    subset=lock.subset,
                    split=lock.split,
                    row_index=record.index,
                    source_identity=record.identity,
                    selection_hash=digest_hex,
                    selection_rank=rank,
                    duration_sec=record.duration_sec,
                    sample_rate_hz=record.sample_rate_hz,
                    transcription=record.transcription,
                    tags=entry.tags,
	            audio_path=materialized.audio_path,
        	    audio_sha256=materialized.sha256,
                )
            )

        return selected

    @staticmethod
    def _sample_id(
        *,
        entry: ManifestEntry,
        record: DatasetRecord,
    ) -> str:
        """
        Create a compact globally stable selected-sample ID.

        Human-readable manifest entry ID is combined with a short hash of
        the backend-neutral source identity.
        """

        source_digest = hashlib.sha256(
            record.identity.encode(
                "utf-8"
            )
        ).hexdigest()[:16]

        return (
            f"{entry.dataset_id}-"
            f"{entry.id}-"
            f"{source_digest}"
        )
