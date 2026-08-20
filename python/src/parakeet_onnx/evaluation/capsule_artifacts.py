"""Artifact transport primitives for ExperimentCapsuleV1.

Embedded artifacts are intentionally bounded because the current Python writer
materializes the row set before handing it to Hugging Face Datasets/Arrow.
Large artifacts must remain external references until the future streaming
Arrow writer is introduced.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_ARTIFACT_CHUNK_SIZE = 1024 * 1024
MAX_EMBEDDED_ARTIFACT_BYTES = 8 * 1024 * 1024


class CapsuleArtifactError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _metadata_json(metadata: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(metadata),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True, slots=True)
class EmbeddedCapsuleArtifact:
    artifact_id: str
    name: str
    mime_type: str
    payload: bytes
    metadata: Mapping[str, Any] = field(default_factory=dict)
    chunk_size_bytes: int = DEFAULT_ARTIFACT_CHUNK_SIZE

    @classmethod
    def from_file(
        cls,
        *,
        artifact_id: str,
        name: str,
        mime_type: str,
        path: str | Path,
        metadata: Mapping[str, Any] | None = None,
        chunk_size_bytes: int = DEFAULT_ARTIFACT_CHUNK_SIZE,
    ) -> EmbeddedCapsuleArtifact:
        source = Path(path)
        size = source.stat().st_size
        if size > MAX_EMBEDDED_ARTIFACT_BYTES:
            raise CapsuleArtifactError(
                "embedded artifact exceeds bounded Python writer limit: "
                f"size={size}, limit={MAX_EMBEDDED_ARTIFACT_BYTES}; "
                "store it externally and use ExternalCapsuleArtifact"
            )
        return cls(
            artifact_id=artifact_id,
            name=name,
            mime_type=mime_type,
            payload=source.read_bytes(),
            metadata={} if metadata is None else metadata,
            chunk_size_bytes=chunk_size_bytes,
        )

    def iter_parts(self) -> Iterator[dict[str, Any]]:
        if not self.artifact_id or not self.name or not self.mime_type:
            raise CapsuleArtifactError("artifact identity fields must be non-empty")
        if not isinstance(self.payload, bytes):
            raise CapsuleArtifactError("embedded artifact payload must be bytes")
        size = len(self.payload)
        if size > MAX_EMBEDDED_ARTIFACT_BYTES:
            raise CapsuleArtifactError(
                "embedded artifact exceeds bounded Python writer limit: "
                f"size={size}, limit={MAX_EMBEDDED_ARTIFACT_BYTES}"
            )
        if self.chunk_size_bytes <= 0:
            raise CapsuleArtifactError("chunk_size_bytes must be positive")

        artifact_sha256 = _sha256(self.payload)
        part_count = max(1, (size + self.chunk_size_bytes - 1) // self.chunk_size_bytes)
        for part_index in range(part_count):
            offset = part_index * self.chunk_size_bytes
            part = self.payload[offset : offset + self.chunk_size_bytes]
            yield {
                "artifact_id": self.artifact_id,
                "artifact_name": self.name,
                "mime_type": self.mime_type,
                "artifact_sha256": artifact_sha256,
                "artifact_size_raw": size,
                "artifact_part_index": part_index,
                "artifact_part_count": part_count,
                "artifact_offset": offset,
                "artifact_part_sha256": _sha256(part),
                "metadata_json": _metadata_json({"location": "embedded", **dict(self.metadata)}),
                "payload": part,
            }


@dataclass(frozen=True, slots=True)
class ExternalCapsuleArtifact:
    artifact_id: str
    name: str
    mime_type: str
    uri: str
    sha256: str
    size_bytes: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_part(self) -> dict[str, Any]:
        if not all((self.artifact_id, self.name, self.mime_type, self.uri, self.sha256)):
            raise CapsuleArtifactError("external artifact identity fields must be non-empty")
        if len(self.sha256) != 64:
            raise CapsuleArtifactError("external artifact sha256 must be 64 hexadecimal characters")
        try:
            int(self.sha256, 16)
        except ValueError as exc:
            raise CapsuleArtifactError("external artifact sha256 must be hexadecimal") from exc
        if self.size_bytes < 0:
            raise CapsuleArtifactError("external artifact size_bytes must be non-negative")
        return {
            "artifact_id": self.artifact_id,
            "artifact_name": self.name,
            "mime_type": self.mime_type,
            "artifact_sha256": self.sha256.lower(),
            "artifact_size_raw": self.size_bytes,
            "artifact_part_index": 0,
            "artifact_part_count": 1,
            "artifact_offset": 0,
            "artifact_part_sha256": None,
            "metadata_json": _metadata_json(
                {
                    "location": "external",
                    "uri": self.uri,
                    **dict(self.metadata),
                }
            ),
            "payload": None,
        }


CapsuleArtifact = EmbeddedCapsuleArtifact | ExternalCapsuleArtifact


def iter_artifact_parts(artifact: CapsuleArtifact) -> Iterator[dict[str, Any]]:
    if isinstance(artifact, EmbeddedCapsuleArtifact):
        yield from artifact.iter_parts()
    elif isinstance(artifact, ExternalCapsuleArtifact):
        yield artifact.as_part()
    else:  # pragma: no cover - defensive typing boundary
        raise CapsuleArtifactError(f"unsupported artifact type: {type(artifact)!r}")
