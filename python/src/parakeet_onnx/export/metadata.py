from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class RuntimeContractMetadata:
    input_kind: Literal["canonical_waveform", "features"]
    primary_input: str
    length_input: str | None
    logits_output: str
    blank_id: int
    decoder: str = "ctc"


@dataclass(frozen=True, slots=True)
class CandidateMetadata:
    schema_version: int
    candidate_id: str
    primary_artifact: str
    decoder: str
    artifact_sha256: str
    runtime_contract: RuntimeContractMetadata | None = None


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
