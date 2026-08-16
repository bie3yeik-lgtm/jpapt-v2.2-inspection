from __future__ import annotations

import json
from pathlib import Path

from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract

from .metadata import CandidateMetadata, CandidateVariantMetadata, write_candidate_metadata
from .validate import validate_onnx_model


def finalize_candidate_variant(
    *,
    output_dir: Path,
    profile_set: str,
    variant: str,
    artifact_roles: dict[str, str],
    tokenizer_path: str | None = None,
    repository_root: str | Path | None = None,
) -> CandidateMetadata:
    """Create or extend minimal candidate metadata and validate derived runtime data."""

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

    normalized_artifacts: dict[str, str] = {}
    for role, relative in artifact_roles.items():
        path = (root / relative).resolve()
        path.relative_to(root)
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() == ".onnx":
            validate_onnx_model(path)
        normalized_artifacts[role] = path.relative_to(root).as_posix()

    missing = sorted(set(profile.required_artifact_roles) - set(normalized_artifacts))
    if missing:
        raise ValueError(
            f"variant {variant!r} is missing profile-required artifact roles: {missing}"
        )
    allowed = set(profile.required_artifact_roles) | set(profile.optional_artifact_roles)
    unexpected = sorted(set(normalized_artifacts) - allowed)
    if unexpected:
        raise ValueError(
            f"variant {variant!r} contains roles not allowed by profile {profile_id!r}: "
            f"{unexpected}"
        )

    normalized_tokenizer: str | None = None
    if tokenizer_path is not None:
        resolved = (root / tokenizer_path).resolve()
        resolved.relative_to(root)
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        normalized_tokenizer = resolved.relative_to(root).as_posix()

    metadata_path = root / "metadata.json"
    variants: dict[str, CandidateVariantMetadata] = {}
    if metadata_path.is_file():
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            raise ValueError("metadata.json root must be an object")
        if existing.get("profile_set") != profile_set:
            raise ValueError("profile_set differs from existing metadata.json")
        existing_variants = existing.get("variants")
        if not isinstance(existing_variants, dict):
            raise ValueError("existing metadata.json variants must be an object")
        for name, value in existing_variants.items():
            if not isinstance(value, dict) or not isinstance(value.get("artifacts"), dict):
                raise ValueError(f"existing variant {name!r} is invalid")
            variants[name] = CandidateVariantMetadata(
                artifacts={str(k): str(v) for k, v in value["artifacts"].items()},
                tokenizer=(str(value["tokenizer"]) if value.get("tokenizer") is not None else None),
            )

    variants[variant] = CandidateVariantMetadata(
        artifacts=normalized_artifacts,
        tokenizer=normalized_tokenizer,
    )
    metadata = CandidateMetadata(profile_set=profile_set, variants=variants)
    write_candidate_metadata(metadata_path, metadata)

    # The human-authored file is now complete. Everything else is derived and
    # validated immediately so invalid graph/tokenizer combinations fail early.
    candidate = CandidateArtifacts.load(
        root,
        variant=variant,
        repository_root=repo_root,
    )
    validate_candidate_runtime_contract(candidate)
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
