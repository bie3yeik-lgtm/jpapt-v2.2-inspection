"""Static Hugging Face target profiles for multi-framework ASR development."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any


class HfTargetError(RuntimeError):
    """Raised when a Hugging Face target profile is invalid."""


@dataclass(frozen=True, slots=True)
class HfTarget:
    id: str
    model_id: str
    upstream_repo_id: str
    canonical_framework: str
    supported_decoders: tuple[str, ...]
    default_decoder: str
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
            "supported_decoders": list(self.supported_decoders),
            "default_decoder": self.default_decoder,
            "bucket": self.bucket,
            "model_repo": self.model_repo,
            "datasets_policy": self.datasets_policy,
        }


def _require_string(source: dict[str, Any], key: str, *, path: Path) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise HfTargetError(f"{path}: {key!r} must be a non-empty string.")
    return value


def _require_string_list(
    source: dict[str, Any],
    key: str,
    *,
    path: Path,
) -> tuple[str, ...]:
    value = source.get(key)
    if not isinstance(value, list) or not value:
        raise HfTargetError(f"{path}: {key!r} must be a non-empty array.")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise HfTargetError(
                f"{path}: {key}[{index}] must be a non-empty string."
            )
        result.append(item)
    if len(result) != len(set(result)):
        raise HfTargetError(f"{path}: {key!r} must not contain duplicates.")
    return tuple(result)


def load_hf_target(path: str | Path) -> HfTarget:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise HfTargetError(f"HF target profile does not exist: {resolved}")
    with resolved.open("rb") as file:
        raw = tomllib.load(file)
    if raw.get("schema_version") != 1:
        raise HfTargetError(f"{resolved}: schema_version must equal 1.")

    target = raw.get("target")
    upstream = raw.get("upstream")
    reference = raw.get("reference")
    decoders = raw.get("decoders")
    storage = raw.get("storage")
    evaluation = raw.get("evaluation")
    for name, value in (
        ("target", target),
        ("upstream", upstream),
        ("reference", reference),
        ("decoders", decoders),
        ("storage", storage),
        ("evaluation", evaluation),
    ):
        if not isinstance(value, dict):
            raise HfTargetError(f"{resolved}: [{name}] table is required.")

    supported = _require_string_list(decoders, "supported", path=resolved)
    default = _require_string(decoders, "default", path=resolved)
    if default not in supported:
        raise HfTargetError(
            f"{resolved}: decoders.default={default!r} is not in "
            f"decoders.supported={list(supported)!r}."
        )

    return HfTarget(
        id=_require_string(target, "id", path=resolved),
        model_id=_require_string(target, "model_id", path=resolved),
        upstream_repo_id=_require_string(upstream, "repo_id", path=resolved),
        canonical_framework=_require_string(
            reference,
            "canonical_framework",
            path=resolved,
        ),
        supported_decoders=supported,
        default_decoder=default,
        bucket=_require_string(storage, "bucket", path=resolved),
        model_repo=_require_string(storage, "model_repo", path=resolved),
        datasets_policy=_require_string(
            evaluation,
            "datasets_policy",
            path=resolved,
        ),
        path=resolved,
    )


def load_hf_target_by_id(
    target_id: str,
    *,
    repository_root: str | Path,
) -> HfTarget:
    root = Path(repository_root).expanduser().resolve()
    return load_hf_target(root / "config" / "hf-targets" / f"{target_id}.toml")
