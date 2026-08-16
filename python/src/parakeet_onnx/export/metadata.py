from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CatalogReference:
    id: str
    sha256: str


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
class TokenizerBinding:
    path: str


@dataclass(frozen=True, slots=True)
class CandidateVariantMetadata:
    artifacts: dict[str, ArtifactMetadata]
    bindings: dict[str, Any]
    tokenizer: TokenizerBinding | None


@dataclass(frozen=True, slots=True)
class CandidateMetadata:
    candidate_id: str
    catalog: CatalogReference
    profile_set: str
    variants: dict[str, CandidateVariantMetadata]
    schema_version: int = 3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_candidate_metadata(path: Path, metadata: CandidateMetadata) -> None:
    if metadata.schema_version != 3:
        raise ValueError("new candidate metadata must use schema_version=3")
    if not metadata.catalog.id or len(metadata.catalog.sha256) != 64:
        raise ValueError("candidate metadata must pin a valid ASR catalog reference")
    if not metadata.profile_set:
        raise ValueError("candidate metadata must reference a profile_set")
    if not metadata.variants:
        raise ValueError("candidate metadata must define at least one variant")
    for variant, value in metadata.variants.items():
        if not variant or not value.artifacts:
            raise ValueError(f"candidate variant {variant!r} is incomplete")
        for key in ("input_kind", "io", "decoder_config"):
            if key not in value.bindings:
                raise ValueError(
                    f"candidate variant {variant!r} bindings are missing {key!r}"
                )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(metadata), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
