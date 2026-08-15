"""
Typed configuration models.

The project deliberately keeps the complete parsed TOML tree in ``raw``.

Frequently used identity and compatibility fields are exposed as typed
properties, while less common/provider-specific fields remain accessible
through ``get()``.

This avoids coupling every TOML field addition to a Python dataclass change
while still providing validation for the configuration fields that control
execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from .errors import ConfigValidationError


T = TypeVar("T")

_MISSING = object()


def _get_nested(
    mapping: dict[str, Any],
    key: str,
    default: Any = _MISSING,
) -> Any:
    """
    Resolve a dotted configuration key.

    Example:
        ``provider.ort_name``
    """

    current: Any = mapping

    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            if default is not _MISSING:
                return default

            raise KeyError(key)

        current = current[part]

    return current


@dataclass(frozen=True, slots=True)
class BaseConfig:
    """
    Base wrapper around a parsed TOML configuration tree.
    """

    path: Path
    raw: dict[str, Any]

    @property
    def schema_version(self) -> int:
        value = self.raw.get("schema_version")

        if not isinstance(value, int):
            raise ConfigValidationError(
                "schema_version must be an integer.",
                path=self.path,
            )

        return value

    def get(
        self,
        key: str,
        default: T | None = None,
    ) -> Any | T | None:
        """
        Read a dotted configuration key.

        Example:

            config.get("execution.platforms.macos")
        """

        return _get_nested(
            self.raw,
            key,
            default,
        )

    def require(self, key: str) -> Any:
        """
        Read a required dotted configuration key.
        """

        try:
            return _get_nested(self.raw, key)

        except KeyError as exc:
            raise ConfigValidationError(
                f"Missing required configuration field: {key}",
                path=self.path,
            ) from exc


@dataclass(frozen=True, slots=True)
class ModelConfig(BaseConfig):
    """Typed model configuration."""

    @property
    def id(self) -> str:
        value = self.require("model.id")

        if not isinstance(value, str) or not value:
            raise ConfigValidationError(
                "model.id must be a non-empty string.",
                path=self.path,
            )

        return value

    @property
    def family(self) -> str:
        return str(self.require("model.family"))

    @property
    def architecture(self) -> str:
        return str(self.require("model.architecture"))

    @property
    def language(self) -> str:
        return str(self.require("model.language"))

    @property
    def upstream_repo_id(self) -> str:
        return str(self.require("upstream.repo_id"))

    @property
    def supported_providers(self) -> tuple[str, ...]:
        values = self.require("execution.supported_providers")

        if not isinstance(values, list):
            raise ConfigValidationError(
                "execution.supported_providers must be an array.",
                path=self.path,
            )

        return tuple(str(value) for value in values)

    def providers_for_environment(
        self,
        environment_id: str,
    ) -> tuple[str, ...]:
        values = self.require(
            f"execution.platforms.{environment_id}"
        )

        if not isinstance(values, list):
            raise ConfigValidationError(
                f"execution.platforms.{environment_id} must be an array.",
                path=self.path,
            )

        return tuple(str(value) for value in values)


@dataclass(frozen=True, slots=True)
class ProviderConfig(BaseConfig):
    """Typed ONNX Runtime Execution Provider configuration."""

    @property
    def id(self) -> str:
        return str(self.require("provider.id"))

    @property
    def ort_name(self) -> str:
        return str(self.require("provider.ort_name"))

    @property
    def enabled(self) -> bool:
        return bool(self.require("provider.enabled"))

    @property
    def supported_os(self) -> tuple[str, ...]:
        values = self.require("provider.supported_os")

        if not isinstance(values, list):
            raise ConfigValidationError(
                "provider.supported_os must be an array.",
                path=self.path,
            )

        return tuple(str(value) for value in values)

    @property
    def reference_provider(self) -> bool:
        return bool(
            self.get(
                "provider.reference_provider",
                False,
            )
        )


@dataclass(frozen=True, slots=True)
class ExecutionEnvironmentConfig(BaseConfig):
    """Typed operating-system/environment configuration."""

    @property
    def id(self) -> str:
        return str(self.require("environment.id"))

    @property
    def os(self) -> str:
        return str(self.require("environment.os"))

    @property
    def architecture(self) -> str:
        return str(
            self.get(
                "environment.architecture",
                "auto",
            )
        )

    @property
    def github_runner(self) -> str | None:
        value = self.get(
            "github_actions.runner",
            None,
        )

        if value is None:
            return None

        return str(value)


@dataclass(frozen=True, slots=True)
class EvaluationConfig(BaseConfig):
    """Typed evaluation-suite configuration."""

    @property
    def id(self) -> str:
        return str(self.require("evaluation.id"))

    @property
    def manifest(self) -> str:
        return str(self.require("evaluation.manifest"))

    @property
    def expected_sample_count(self) -> int:
        value = self.require(
            "evaluation.expected_sample_count"
        )

        if not isinstance(value, int) or value <= 0:
            raise ConfigValidationError(
                "evaluation.expected_sample_count "
                "must be a positive integer.",
                path=self.path,
            )

        return value

    @property
    def fail_fast(self) -> bool:
        return bool(
            self.get(
                "evaluation.fail_fast",
                False,
            )
        )


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    """
    Fully resolved execution configuration.

    This object intentionally retains each source configuration separately.

    The source separation is important for:
    - reproducibility
    - run-context generation
    - Python/Rust parity
    - debugging configuration precedence
    """

    repository_root: Path

    model: ModelConfig
    provider: ProviderConfig
    environment: ExecutionEnvironmentConfig
    evaluation: EvaluationConfig

    merged: dict[str, Any]

    @property
    def manifest_path(self) -> Path:
        """
        Resolve evaluation manifest relative to the repository.
        """

        path = Path(self.evaluation.manifest)

        if path.is_absolute():
            return path

        return self.repository_root / path

    @property
    def identity(self) -> str:
        """
        Human-readable execution identity.
        """

        return (
            f"{self.model.id}:"
            f"{self.environment.id}:"
            f"{self.provider.id}:"
            f"{self.evaluation.id}"
        )

    def get(
        self,
        key: str,
        default: T | None = None,
    ) -> Any | T | None:
        """
        Read the merged configuration using a dotted key.
        """

        return _get_nested(
            self.merged,
            key,
            default,
        )

    def require(self, key: str) -> Any:
        try:
            return _get_nested(
                self.merged,
                key,
            )

        except KeyError as exc:
            raise ConfigValidationError(
                f"Missing resolved configuration field: {key}"
            ) from exc
