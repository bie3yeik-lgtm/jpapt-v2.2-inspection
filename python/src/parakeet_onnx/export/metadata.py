from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CandidateVariantMetadata:
    artifacts: dict[str, str]
    tokenizer: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateMetadata:
    profile_set: str
    variants: dict[str, CandidateVariantMetadata]


def write_candidate_metadata(path: Path, metadata: CandidateMetadata) -> None:
    if not metadata.profile_set:
        raise ValueError("candidate metadata must reference a profile_set")
    if not metadata.variants:
        raise ValueError("candidate metadata must define at least one variant")
    for variant, value in metadata.variants.items():
        if not variant or not value.artifacts:
            raise ValueError(f"candidate variant {variant!r} is incomplete")
        for role, artifact_path in value.artifacts.items():
            if not role or not artifact_path:
                raise ValueError(
                    f"candidate variant {variant!r} contains an empty artifact role/path"
                )

    path.parent.mkdir(parents=True, exist_ok=True)
    value = asdict(metadata)
    for variant in value["variants"].values():
        if variant.get("tokenizer") is None:
            variant.pop("tokenizer", None)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
