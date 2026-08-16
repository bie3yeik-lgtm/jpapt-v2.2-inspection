"""Static Hugging Face target profiles for multi-framework ASR development."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any

from parakeet_onnx.config.catalog import AsrCatalogError, load_repository_catalog


class HfTargetError(RuntimeError):
    """Raised when a Hugging Face target profile is invalid."""


@dataclass(frozen=True, slots=True)
class HfTarget:
    id: str
    model_id: str
    upstream_repo_id: str
    canonical_framework: str
    profile_set_id: str
    supported_decoders: tuple[str, ...]
    default_decoder: str
    default_variant: str
    bucket: str
    model_repo: str
    datasets_policy: str
    path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "model_id": self.model_id,
            "upstream_repo_id": self.upstream_repo_id,
            "canonical_framework": self.canonical_framework,
            "profile_set_id": self.profile_set_id,
            "supported_decoders": list(self.supported_decoders),
            "default_decoder": self.default_decoder,
            "default_variant": self.default_variant,
            "bucket": self.bucket,
            "model_repo": self.model_repo,
            "datasets_policy": self.datasets_policy,
        }


def _require_string(source: dict[str, Any], key: str, *, path: Path) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise HfTargetError(f"{path}: {key!r} must be a non-empty string.")
    return value


def load_hf_target(path: str | Path) -> HfTarget:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise HfTargetError(f"HF target profile does not exist: {resolved}")
    with resolved.open("rb") as file:
        raw = tomllib.load(file)
    if raw.get("schema_version") != 2:
        raise HfTargetError(
            f"{resolved}: schema_version must equal 2. Decoder declarations are no "
            "longer stored in target TOML; use [runtime].profile_set."
        )

    target = raw.get("target")
    upstream = raw.get("upstream")
    reference = raw.get("reference")
    runtime = raw.get("runtime")
    storage = raw.get("storage")
    evaluation = raw.get("evaluation")
    for name, value in (
        ("target", target),
        ("upstream", upstream),
        ("reference", reference),
        ("runtime", runtime),
        ("storage", storage),
        ("evaluation", evaluation),
    ):
        if not isinstance(value, dict):
            raise HfTargetError(f"{resolved}: [{name}] table is required.")

    profile_set_id = _require_string(runtime, "profile_set", path=resolved)
    repository_root = resolved.parents[2]
    try:
        catalog = load_repository_catalog(repository_root)
        profile_set = catalog.profile_set(profile_set_id)
        decoders = tuple(
            dict.fromkeys(
                catalog.decoder_profile(profile_id).decoder
                for profile_id in profile_set.variants.values()
            )
        )
        default_decoder = catalog.decoder_profile(
            profile_set.profile_id_for()
        ).decoder
    except AsrCatalogError as exc:
        raise HfTargetError(f"{resolved}: {exc}") from exc

    return HfTarget(
        id=_require_string(target, "id", path=resolved),
        model_id=_require_string(target, "model_id", path=resolved),
        upstream_repo_id=_require_string(upstream, "repo_id", path=resolved),
        canonical_framework=_require_string(
            reference, "canonical_framework", path=resolved
        ),
        profile_set_id=profile_set_id,
        supported_decoders=decoders,
        default_decoder=default_decoder,
        default_variant=profile_set.default_variant,
        bucket=_require_string(storage, "bucket", path=resolved),
        model_repo=_require_string(storage, "model_repo", path=resolved),
        datasets_policy=_require_string(
            evaluation, "datasets_policy", path=resolved
        ),
        path=resolved,
    )


def load_hf_target_by_id(
    target_id: str, *, repository_root: str | Path
) -> HfTarget:
    root = Path(repository_root).expanduser().resolve()
    return load_hf_target(root / "config" / "hf-targets" / f"{target_id}.toml")
