"""
Evaluation audio materialization.

This module establishes the formal contract for:

    ResolvedDatasetSample.audio_path

Definition
==========

``ResolvedDatasetSample.audio_path`` MUST point to a materialized local
audio asset that can be reopened by the evaluation runtime through ordinary
file I/O.

The value MUST NOT be:

- a remote URL
- a Hugging Face datasets Audio object
- an Arrow reference
- an ephemeral file that disappears before the evaluation run finishes
- an opaque object meaningful only to the Python datasets library

Materialization flow
====================

    DatasetRecord
        |
        v
    DatasetMaterializer
        |
        v
    local materialized audio asset
        |
        v
    ResolvedDatasetSample.audio_path
        |
        v
    parakeet_onnx.audio.decode

Responsibilities
================

This module:

- Copies already-local audio assets into a stable evaluation cache.
- Materializes in-memory encoded audio bytes.
- Materializes decoded mono float arrays when no encoded/local asset exists.
- Calculates SHA-256 for the materialized asset.
- Uses deterministic cache locations.
- Writes files atomically.

This module DOES NOT:

- resample audio
- mix channels
- normalize gain
- clip amplitudes
- extract features
- change ASR semantics

Those operations belong to:

    parakeet_onnx.audio.decode
    parakeet_onnx.audio.resample
    parakeet_onnx.audio.features
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .errors import DatasetResolutionError
from .models import DatasetRecord

MaterializationSource = Literal[
    "local_file",
    "encoded_bytes",
    "decoded_array",
]


class DatasetMaterializationError(DatasetResolutionError):
    """
    Raised when a selected dataset record cannot be converted into a
    durable local audio asset.
    """


@dataclass(frozen=True, slots=True)
class MaterializedAudio:
    """
    Result of materializing one selected audio record.

    ``path`` is guaranteed to identify a normal local file at the time
    this object is returned successfully.
    """

    path: Path
    sha256: str
    size_bytes: int

    source_kind: MaterializationSource

    dataset_revision: str
    source_identity: str

    @property
    def audio_path(self) -> str:
        """
        Portable string representation intended for
        ResolvedDatasetSample.audio_path.
        """

        return self.path.as_posix()

    def validate(self) -> None:
        if not self.path.is_file():
            raise DatasetMaterializationError(f"Materialized audio asset does not exist: {self.path}")

        if self.size_bytes <= 0:
            raise DatasetMaterializationError(f"Materialized audio asset is empty: {self.path}")

        if len(self.sha256) != 64:
            raise DatasetMaterializationError("Materialized audio SHA-256 is invalid.")

        try:
            int(self.sha256, 16)
        except ValueError as exc:
            raise DatasetMaterializationError("Materialized audio SHA-256 is not hexadecimal.") from exc


def _sha256_file(
    path: Path,
    *,
    chunk_size: int = 1024 * 1024,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def _sha256_bytes(
    value: bytes,
) -> str:
    return hashlib.sha256(value).hexdigest()


def _materialization_key(
    *,
    dataset_revision: str,
    source_identity: str,
) -> str:
    """
    Produce a deterministic cache key.

    The locked dataset revision is deliberately part of the identity.

    This means:

        same sample identity
        + different dataset revision

    produces a different materialization cache entry.
    """

    if not dataset_revision:
        raise DatasetMaterializationError("dataset_revision must not be empty.")

    if not source_identity:
        raise DatasetMaterializationError("source_identity must not be empty.")

    value = (f"parakeet-onnx-materialized-audio-v1\n{dataset_revision}\n{source_identity}").encode()

    return hashlib.sha256(value).hexdigest()


def _safe_suffix(
    path: str | Path | None,
) -> str:
    """
    Return a conservative audio-file suffix.

    The suffix is used only for materialized file naming and does not form
    part of the authoritative sample identity.
    """

    if path is None:
        return ".audio"

    suffix = Path(str(path)).suffix.lower()

    supported = {
        ".wav",
        ".flac",
        ".ogg",
        ".oga",
        ".mp3",
        ".m4a",
        ".aac",
        ".opus",
        ".aiff",
        ".aif",
        ".caf",
    }

    if suffix in supported:
        return suffix

    return ".audio"


def _atomic_copy(
    source: Path,
    destination: Path,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=(f".{destination.name}."),
        suffix=".tmp",
        dir=destination.parent,
    )

    os.close(file_descriptor)

    temporary = Path(temporary_name)

    try:
        shutil.copyfile(
            source,
            temporary,
        )

        # Force file contents to durable storage before replace.
        with temporary.open("rb") as file:
            os.fsync(file.fileno())

        os.replace(
            temporary,
            destination,
        )

    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_bytes(
    destination: Path,
    value: bytes,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=(f".{destination.name}."),
        suffix=".tmp",
        dir=destination.parent,
    )

    temporary = Path(temporary_name)

    try:
        with os.fdopen(
            file_descriptor,
            "wb",
        ) as file:
            file.write(value)

            file.flush()

            os.fsync(file.fileno())

        os.replace(
            temporary,
            destination,
        )

    finally:
        if temporary.exists():
            temporary.unlink()


def _write_float_wav(
    *,
    destination: Path,
    waveform: Any,
    sample_rate_hz: int,
) -> None:
    """
    Materialize a decoded waveform as IEEE float WAV.

    This is a fallback only for dataset backends that expose decoded samples
    without a reusable local file or encoded bytes.

    No resampling, gain normalization, clipping, or channel conversion is
    performed here.
    """

    if sample_rate_hz <= 0:
        raise DatasetMaterializationError("Cannot materialize decoded audio without a valid sample rate.")

    value = np.asarray(
        waveform,
        dtype=np.float32,
    )

    if value.ndim != 1:
        raise DatasetMaterializationError(
            "Decoded-array materialization currently requires "
            "a mono one-dimensional waveform. "
            "Multi-channel decoded arrays must provide either "
            "encoded bytes or a reusable local source file so channel "
            "layout is not guessed."
        )

    if value.size == 0:
        raise DatasetMaterializationError("Cannot materialize an empty decoded audio array.")

    if not np.all(np.isfinite(value)):
        raise DatasetMaterializationError("Cannot materialize audio containing NaN or infinity.")

    value = np.ascontiguousarray(
        value,
        dtype=np.float32,
    )

    try:
        import soundfile as sf
    except ImportError as exc:
        raise DatasetMaterializationError(
            "Materializing decoded audio arrays requires the 'soundfile' package."
        ) from exc

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=(f".{destination.name}."),
        suffix=".wav.tmp",
        dir=destination.parent,
    )

    os.close(file_descriptor)

    temporary = Path(temporary_name)

    try:
        try:
            sf.write(
                str(temporary),
                value,
                sample_rate_hz,
                format="WAV",
                subtype="FLOAT",
            )

        except Exception as exc:
            raise DatasetMaterializationError(f"Failed to materialize decoded audio array as float WAV: {exc}") from exc

        with temporary.open("rb") as file:
            os.fsync(file.fileno())

        os.replace(
            temporary,
            destination,
        )

    finally:
        if temporary.exists():
            temporary.unlink()


class DatasetMaterializer:
    """
    Materialize selected DatasetRecord audio into a stable local cache.

    Recommended root:

        .cache/evaluation/audio/

    Result layout:

        <root>/
        └── <first-two-key-chars>/
            └── <materialization-key>/
                ├── audio.<ext>
                └── metadata.json

    The cache is disposable.

    Authoritative identity remains:

        datasets-lock.json
        +
        dataset revision
        +
        source identity
    """

    METADATA_SCHEMA_VERSION = 1

    def __init__(
        self,
        root: str | Path,
    ) -> None:
        self.root = Path(root).expanduser().resolve()

    def materialize(
        self,
        *,
        record: DatasetRecord,
        dataset_revision: str,
    ) -> MaterializedAudio:
        """
        Materialize one selected DatasetRecord.

        Resolution preference:

        1. reusable local source file
        2. encoded bytes
        3. decoded waveform array

        This order preserves original encoded material whenever possible.
        """

        try:
            record.validate()
        except ValueError as exc:
            raise DatasetMaterializationError(f"Invalid DatasetRecord: {exc}") from exc

        key = _materialization_key(
            dataset_revision=dataset_revision,
            source_identity=record.identity,
        )

        directory = self.root / key[:2] / key

        existing = self._load_existing(
            directory=directory,
            dataset_revision=dataset_revision,
            source_identity=record.identity,
        )

        if existing is not None:
            return existing

        local_source = self._resolve_local_source(record)

        if local_source is not None:
            result = self._materialize_local_file(
                record=record,
                source=local_source,
                directory=directory,
                dataset_revision=dataset_revision,
            )

        else:
            encoded = self._extract_encoded_bytes(record.audio)

            if encoded is not None:
                encoded_bytes, suggested_path = encoded

                result = self._materialize_encoded_bytes(
                    record=record,
                    value=encoded_bytes,
                    suggested_path=suggested_path,
                    directory=directory,
                    dataset_revision=dataset_revision,
                )

            else:
                result = self._materialize_decoded_array(
                    record=record,
                    directory=directory,
                    dataset_revision=dataset_revision,
                )

        result.validate()

        self._write_metadata(
            directory=directory,
            result=result,
        )

        return result

    def _resolve_local_source(
        self,
        record: DatasetRecord,
    ) -> Path | None:
        """
        Resolve an existing local audio source.

        Remote URLs are never treated as local assets.
        """

        candidates: list[str] = []

        if record.audio_path:
            candidates.append(record.audio_path)

        if isinstance(
            record.audio,
            str,
        ):
            candidates.append(record.audio)

        if isinstance(
            record.audio,
            dict,
        ):
            path_value = record.audio.get("path")

            if path_value:
                candidates.append(str(path_value))

        for value in candidates:
            # Do not interpret remote references as local paths.
            lowered = value.lower()

            if lowered.startswith(
                (
                    "http://",
                    "https://",
                    "hf://",
                    "s3://",
                    "gs://",
                )
            ):
                continue

            path = Path(value).expanduser()

            try:
                path = path.resolve()
            except OSError:
                continue

            if path.is_file():
                return path

        return None

    @staticmethod
    def _extract_encoded_bytes(
        audio: Any,
    ) -> (
        tuple[
            bytes,
            str | None,
        ]
        | None
    ):
        """
        Extract encoded source bytes from common HF-style structures.

        Expected shape:

            {
                "bytes": b"...",
                "path": "sample.flac"
            }

        ``path`` is used only to retain a meaningful file extension.
        """

        if isinstance(
            audio,
            (bytes, bytearray, memoryview),
        ):
            return (
                bytes(audio),
                None,
            )

        if not isinstance(
            audio,
            dict,
        ):
            return None

        value = audio.get("bytes")

        if value is None:
            return None

        if not isinstance(
            value,
            (
                bytes,
                bytearray,
                memoryview,
            ),
        ):
            raise DatasetMaterializationError("audio['bytes'] exists but is not bytes-like.")

        suggested_path = str(audio["path"]) if audio.get("path") else None

        return (
            bytes(value),
            suggested_path,
        )

    def _materialize_local_file(
        self,
        *,
        record: DatasetRecord,
        source: Path,
        directory: Path,
        dataset_revision: str,
    ) -> MaterializedAudio:
        suffix = _safe_suffix(source)

        destination = directory / f"audio{suffix}"

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        _atomic_copy(
            source,
            destination,
        )

        digest = _sha256_file(destination)

        return MaterializedAudio(
            path=destination,
            sha256=digest,
            size_bytes=(destination.stat().st_size),
            source_kind="local_file",
            dataset_revision=dataset_revision,
            source_identity=record.identity,
        )

    def _materialize_encoded_bytes(
        self,
        *,
        record: DatasetRecord,
        value: bytes,
        suggested_path: str | None,
        directory: Path,
        dataset_revision: str,
    ) -> MaterializedAudio:
        if not value:
            raise DatasetMaterializationError("Encoded audio payload is empty.")

        suffix = _safe_suffix(suggested_path)

        destination = directory / f"audio{suffix}"

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        _atomic_write_bytes(
            destination,
            value,
        )

        digest = _sha256_bytes(value)

        return MaterializedAudio(
            path=destination,
            sha256=digest,
            size_bytes=len(value),
            source_kind="encoded_bytes",
            dataset_revision=dataset_revision,
            source_identity=record.identity,
        )

    def _materialize_decoded_array(
        self,
        *,
        record: DatasetRecord,
        directory: Path,
        dataset_revision: str,
    ) -> MaterializedAudio:
        waveform = self._extract_decoded_array(record.audio)

        if waveform is None:
            raise DatasetMaterializationError(
                "Dataset record cannot be materialized. "
                "No reusable local file, encoded bytes, "
                "or decoded waveform array is available: "
                f"identity={record.identity!r}"
            )

        sample_rate = self._extract_sample_rate(record)

        if sample_rate is None:
            raise DatasetMaterializationError(
                f"Decoded waveform is available but its sample rate cannot be determined: identity={record.identity!r}"
            )

        destination = directory / "audio.wav"

        _write_float_wav(
            destination=destination,
            waveform=waveform,
            sample_rate_hz=sample_rate,
        )

        digest = _sha256_file(destination)

        return MaterializedAudio(
            path=destination,
            sha256=digest,
            size_bytes=(destination.stat().st_size),
            source_kind="decoded_array",
            dataset_revision=dataset_revision,
            source_identity=record.identity,
        )

    @staticmethod
    def _extract_decoded_array(
        audio: Any,
    ) -> Any | None:
        if isinstance(
            audio,
            np.ndarray,
        ):
            return audio

        if isinstance(
            audio,
            dict,
        ):
            return audio.get("array")

        return None

    @staticmethod
    def _extract_sample_rate(
        record: DatasetRecord,
    ) -> int | None:
        if record.sample_rate_hz is not None:
            return int(record.sample_rate_hz)

        if isinstance(
            record.audio,
            dict,
        ):
            value = record.audio.get("sampling_rate") or record.audio.get("sample_rate")

            if value is not None:
                return int(value)

        return None

    def _metadata_path(
        self,
        directory: Path,
    ) -> Path:
        return directory / "metadata.json"

    def _write_metadata(
        self,
        *,
        directory: Path,
        result: MaterializedAudio,
    ) -> None:
        metadata = {
            "schema_version": (self.METADATA_SCHEMA_VERSION),
            "dataset_revision": (result.dataset_revision),
            "source_identity": (result.source_identity),
            "source_kind": (result.source_kind),
            "audio_file": (result.path.name),
            "sha256": result.sha256,
            "size_bytes": (result.size_bytes),
        }

        payload = (
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )

        _atomic_write_bytes(
            self._metadata_path(directory),
            payload,
        )

    def _load_existing(
        self,
        *,
        directory: Path,
        dataset_revision: str,
        source_identity: str,
    ) -> MaterializedAudio | None:
        """
        Reuse an existing cache entry only after verifying its metadata and
        content digest.
        """

        metadata_path = self._metadata_path(directory)

        if not metadata_path.is_file():
            return None

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return None

        if not isinstance(
            metadata,
            dict,
        ):
            return None

        if metadata.get("schema_version") != self.METADATA_SCHEMA_VERSION:
            return None

        if metadata.get("dataset_revision") != dataset_revision:
            return None

        if metadata.get("source_identity") != source_identity:
            return None

        audio_file = metadata.get("audio_file")

        expected_sha256 = metadata.get("sha256")

        source_kind = metadata.get("source_kind")

        if not isinstance(
            audio_file,
            str,
        ):
            return None

        if not isinstance(
            expected_sha256,
            str,
        ):
            return None

        if source_kind not in (
            "local_file",
            "encoded_bytes",
            "decoded_array",
        ):
            return None

        audio_path = directory / audio_file

        if not audio_path.is_file():
            return None

        actual_sha256 = _sha256_file(audio_path)

        if actual_sha256 != expected_sha256:
            return None

        size_bytes = audio_path.stat().st_size

        if size_bytes <= 0:
            return None

        result = MaterializedAudio(
            path=audio_path,
            sha256=actual_sha256,
            size_bytes=size_bytes,
            source_kind=source_kind,
            dataset_revision=dataset_revision,
            source_identity=source_identity,
        )

        result.validate()

        return result

    def remove(
        self,
        *,
        dataset_revision: str,
        source_identity: str,
    ) -> bool:
        """
        Remove one disposable materialization cache entry.
        """

        key = _materialization_key(
            dataset_revision=dataset_revision,
            source_identity=source_identity,
        )

        directory = self.root / key[:2] / key

        if not directory.exists():
            return False

        shutil.rmtree(directory)

        return True
