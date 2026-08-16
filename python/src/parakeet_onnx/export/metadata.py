from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    path: str
    sha256: str
    size_bytes: int

    @classmethod
    def from_file(cls, path: Path, *, relative_to: Path) -> "ArtifactMetadata":
        value = path.expanduser().resolve()
        root = relative_to.expanduser().resolve()
        return cls(
            path=value.relative_to(root).as_posix(),
            sha256=sha256_file(value),
            size_bytes=value.stat().st_size,
        )


@dataclass(frozen=True, slots=True)
class TokenizerMetadata:
    kind: str
    path: str


@dataclass(frozen=True, slots=True)
class CandidateMetadata:
    candidate_id: str
    decoder: str
    artifact_contract: str
    artifacts: dict[str, ArtifactMetadata]
    runtime_contract: dict[str, Any]
    tokenizer: TokenizerMetadata | None = None
    features: dict[str, bool] = field(default_factory=dict)
    schema_version: int = 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_candidate_metadata(
    path: Path,
    metadata: CandidateMetadata,
) -> None:
    if metadata.schema_version != 2:
        raise ValueError("new candidate metadata must use schema_version=2")
    if metadata.runtime_contract.get("decoder") != metadata.decoder:
        raise ValueError("runtime_contract.decoder must match candidate decoder")
    if not metadata.artifacts:
        raise ValueError("candidate metadata must define at least one artifact")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            asdict(metadata),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
