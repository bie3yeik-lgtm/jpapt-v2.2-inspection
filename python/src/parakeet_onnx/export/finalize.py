from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from parakeet_onnx.config.catalog import load_repository_catalog

from .metadata import (
    ArtifactMetadata,
    CandidateMetadata,
    CandidateVariantMetadata,
    CatalogReference,
    TokenizerBinding,
    write_candidate_metadata,
)
from .validate import validate_onnx_model


def load_runtime_contract(path: str | Path) -> dict[str, Any]:
    value_path = Path(path).expanduser().resolve()
    raw = json.loads(value_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("runtime contract JSON root must be an object")
    # Staging contracts may still include decoder for human readability. It is
    # not serialized into canonical candidate metadata; the central profile is
    # authoritative for decoder semantics.
    for key in ("input_kind", "io", "decoder_config"):
        if key not in raw:
            raise ValueError(f"runtime contract is missing required field: {key}")
    return raw


def finalize_candidate_variant(
    *,
    output_dir: Path,
    candidate_id: str,
    profile_set: str,
    variant: str,
    artifact_roles: dict[str, str],
    runtime_contract: dict[str, Any],
    tokenizer_path: str | None = None,
    repository_root: str | Path | None = None,
) -> CandidateMetadata:
    """Create or extend canonical schema-v3 candidate metadata.

    Reusable decoder semantics are resolved from config/asr-catalog.json. The
    candidate pins that catalog snapshot and stores only candidate-specific
    artifact identities, tensor/runtime bindings, and tokenizer asset paths.
    `profile_set + variant` determines the decoder profile; profile IDs are not
    repeated inside every variant.
    """

    root = Path(output_dir).expanduser().resolve()
    repo_root = (
        Path(repository_root).expanduser().resolve()
        if repository_root is not None
        else _discover_repository_root(root)
    )
    catalog = load_repository_catalog(repo_root)
    profile_set_value = catalog.profile_set(profile_set)
    profile_id = profile_set_value.profile_id_for(variant)
    profile = catalog.decoder_profile(profile_id)

    artifacts: dict[str, ArtifactMetadata] = {}
    for role, relative in artifact_roles.items():
        path = (root / relative).resolve()
        path.relative_to(root)
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() == ".onnx":
            validate_onnx_model(path)
        artifacts[role] = ArtifactMetadata.from_file(path, relative_to=root)

    missing = sorted(set(profile.required_artifact_roles) - set(artifacts))
    if missing:
        raise ValueError(
            f"variant {variant!r} is missing profile-required artifact roles: {missing}"
        )
    allowed = set(profile.required_artifact_roles) | set(profile.optional_artifact_roles)
    unexpected = sorted(set(artifacts) - allowed)
    if unexpected:
        raise ValueError(
            f"variant {variant!r} contains roles not allowed by profile {profile_id!r}: "
            f"{unexpected}"
        )

    tokenizer: TokenizerBinding | None = None
    if tokenizer_path is not None:
        resolved = (root / tokenizer_path).resolve()
        resolved.relative_to(root)
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        tokenizer = TokenizerBinding(path=tokenizer_path)

    bindings = {
        "input_kind": runtime_contract["input_kind"],
        "io": runtime_contract["io"],
        "decoder_config": runtime_contract["decoder_config"],
    }
    variant_metadata = CandidateVariantMetadata(
        artifacts=artifacts,
        bindings=bindings,
        tokenizer=tokenizer,
    )

    metadata_path = root / "metadata.json"
    variants: dict[str, CandidateVariantMetadata] = {}
    catalog_ref = CatalogReference(id=catalog.catalog_id, sha256=catalog.sha256)
    if metadata_path.is_file():
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        if existing.get("schema_version") != 3:
            raise ValueError(
                "cannot merge a new canonical variant into pre-v3 candidate metadata"
            )
        if existing.get("candidate_id") != candidate_id:
            raise ValueError("candidate_id differs from existing metadata.json")
        if existing.get("profile_set") != profile_set:
            raise ValueError("profile_set differs from existing metadata.json")
        existing_catalog = existing.get("catalog")
        if existing_catalog != {"id": catalog.catalog_id, "sha256": catalog.sha256}:
            raise ValueError(
                "candidate catalog pin differs from the checked-out central catalog"
            )
        for name, value in existing.get("variants", {}).items():
            variants[name] = CandidateVariantMetadata(
                artifacts={
                    role: ArtifactMetadata(**artifact)
                    for role, artifact in value["artifacts"].items()
                },
                bindings=dict(value["bindings"]),
                tokenizer=(
                    TokenizerBinding(**value["tokenizer"])
                    if value.get("tokenizer") is not None
                    else None
                ),
            )
    variants[variant] = variant_metadata

    metadata = CandidateMetadata(
        candidate_id=candidate_id,
        catalog=catalog_ref,
        profile_set=profile_set,
        variants=variants,
    )
    write_candidate_metadata(metadata_path, metadata)
    return metadata


def _discover_repository_root(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / "config" / "asr-catalog.json").is_file():
            return parent
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        if (parent / "config" / "asr-catalog.json").is_file():
            return parent
    raise RuntimeError("could not locate repository config/asr-catalog.json")
