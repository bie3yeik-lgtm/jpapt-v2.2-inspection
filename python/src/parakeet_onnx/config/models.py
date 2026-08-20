"""Typed execution configuration models.

Only unconsumed extension fields remain available through ``get``. Every field
that controls execution is validated without Python coercion: a string is not a
boolean, a boolean is not an integer, and array members must already have their
required type.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from .errors import ConfigValidationError

T = TypeVar("T")
_MISSING = object()


def _get_nested(mapping: dict[str, Any], key: str, default: Any = _MISSING) -> Any:
    current: Any = mapping
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            if default is not _MISSING:
                return default
            raise KeyError(key)
        current = current[part]
    return current


def _string(value: Any, *, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigValidationError(
            f"{field} must be a non-empty string.",
            path=path,
        )
    return value.strip()


def _boolean(value: Any, *, field: str, path: Path) -> bool:
    if type(value) is not bool:
        raise ConfigValidationError(
            f"{field} must be a boolean.",
            path=path,
        )
    return value


def _positive_integer(value: Any, *, field: str, path: Path) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigValidationError(
            f"{field} must be a positive integer.",
            path=path,
        )
    return value


def _string_array(value: Any, *, field: str, path: Path) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigValidationError(
            f"{field} must be an array.",
            path=path,
        )
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_string(item, field=f"{field}[{index}]", path=path))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class BaseConfig:
    path: Path
    raw: dict[str, Any]

    @property
    def schema_version(self) -> int:
        value = self.raw.get("schema_version")
        if not isinstance(value, int) or isinstance(value, bool):
            raise ConfigValidationError(
                "schema_version must be an integer.",
                path=self.path,
            )
        return value

    def get(self, key: str, default: T | None = None) -> Any | T | None:
        return _get_nested(self.raw, key, default)

    def require(self, key: str) -> Any:
        try:
            return _get_nested(self.raw, key)
        except KeyError as exc:
            raise ConfigValidationError(
                f"Missing required configuration field: {key}",
                path=self.path,
            ) from exc


@dataclass(frozen=True, slots=True)
class ModelConfig(BaseConfig):
    @property
    def id(self) -> str:
        return _string(self.require("model.id"), field="model.id", path=self.path)

    @property
    def family(self) -> str:
        return _string(self.require("model.family"), field="model.family", path=self.path)

    @property
    def architecture(self) -> str:
        return _string(
            self.require("model.architecture"),
            field="model.architecture",
            path=self.path,
        )

    @property
    def language(self) -> str:
        return _string(self.require("model.language"), field="model.language", path=self.path)

    @property
    def upstream_repo_id(self) -> str:
        return _string(
            self.require("upstream.repo_id"),
            field="upstream.repo_id",
            path=self.path,
        )

    @property
    def supported_providers(self) -> tuple[str, ...]:
        return _string_array(
            self.require("execution.supported_providers"),
            field="execution.supported_providers",
            path=self.path,
        )

    def providers_for_environment(self, environment_id: str) -> tuple[str, ...]:
        environment_id = _string(environment_id, field="environment_id", path=self.path)
        return _string_array(
            self.require(f"execution.platforms.{environment_id}"),
            field=f"execution.platforms.{environment_id}",
            path=self.path,
        )


@dataclass(frozen=True, slots=True)
class ProviderConfig(BaseConfig):
    @property
    def id(self) -> str:
        return _string(self.require("provider.id"), field="provider.id", path=self.path)

    @property
    def ort_name(self) -> str:
        return _string(
            self.require("provider.ort_name"),
            field="provider.ort_name",
            path=self.path,
        )

    @property
    def enabled(self) -> bool:
        return _boolean(
            self.require("provider.enabled"),
            field="provider.enabled",
            path=self.path,
        )

    @property
    def supported_os(self) -> tuple[str, ...]:
        return _string_array(
            self.require("provider.supported_os"),
            field="provider.supported_os",
            path=self.path,
        )

    @property
    def reference_provider(self) -> bool:
        return _boolean(
            self.get("provider.reference_provider", False),
            field="provider.reference_provider",
            path=self.path,
        )


@dataclass(frozen=True, slots=True)
class ExecutionEnvironmentConfig(BaseConfig):
    @property
    def id(self) -> str:
        return _string(self.require("environment.id"), field="environment.id", path=self.path)

    @property
    def os(self) -> str:
        return _string(self.require("environment.os"), field="environment.os", path=self.path)

    @property
    def architecture(self) -> str:
        return _string(
            self.get("environment.architecture", "auto"),
            field="environment.architecture",
            path=self.path,
        )

    @property
    def github_runner(self) -> str | None:
        value = self.get("github_actions.runner", None)
        if value is None:
            return None
        return _string(value, field="github_actions.runner", path=self.path)


@dataclass(frozen=True, slots=True)
class EvaluationConfig(BaseConfig):
    @property
    def id(self) -> str:
        return _string(self.require("evaluation.id"), field="evaluation.id", path=self.path)

    @property
    def manifest(self) -> str:
        return _string(
            self.require("evaluation.manifest"),
            field="evaluation.manifest",
            path=self.path,
        )

    @property
    def expected_sample_count(self) -> int:
        return _positive_integer(
            self.require("evaluation.expected_sample_count"),
            field="evaluation.expected_sample_count",
            path=self.path,
        )

    @property
    def fail_fast(self) -> bool:
        return _boolean(
            self.get("evaluation.fail_fast", False),
            field="evaluation.fail_fast",
            path=self.path,
        )


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    repository_root: Path
    model: ModelConfig
    provider: ProviderConfig
    environment: ExecutionEnvironmentConfig
    evaluation: EvaluationConfig
    merged: dict[str, Any]

    @property
    def manifest_path(self) -> Path:
        path = Path(self.evaluation.manifest)
        if path.is_absolute():
            return path
        return self.repository_root / path

    @property
    def identity(self) -> str:
        return f"{self.model.id}:{self.environment.id}:{self.provider.id}:{self.evaluation.id}"

    def get(self, key: str, default: T | None = None) -> Any | T | None:
        return _get_nested(self.merged, key, default)

    def require(self, key: str) -> Any:
        try:
            return _get_nested(self.merged, key)
        except KeyError as exc:
            raise ConfigValidationError(f"Missing resolved configuration field: {key}") from exc
