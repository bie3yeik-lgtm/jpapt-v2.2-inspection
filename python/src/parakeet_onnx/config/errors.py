"""
Configuration-specific exception hierarchy.

Configuration failures are separated from runtime/model failures so that
CLI and CI code can classify an error without parsing human-readable text.
"""

from __future__ import annotations

from pathlib import Path


class ConfigError(RuntimeError):
    """Base class for all project configuration errors."""


class ConfigFileNotFoundError(ConfigError):
    """Raised when a required configuration file does not exist."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

        super().__init__(f"Required configuration file does not exist: {self.path}")


class ConfigValidationError(ConfigError):
    """Raised when configuration contents violate the project contract."""

    def __init__(
        self,
        message: str,
        *,
        path: str | Path | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else None

        full_message = message if self.path is None else f"{message} [file: {self.path}]"

        super().__init__(full_message)


class ConfigMergeError(ConfigError):
    """Raised when configuration layers cannot be merged safely."""


class UnsupportedEnvironmentError(ConfigError):
    """Raised when the current OS does not map to a supported environment."""

    def __init__(self, environment: str) -> None:
        self.environment = environment

        super().__init__(f"Unsupported execution environment: {environment}")


class UnsupportedProviderError(ConfigError):
    """Raised when a provider is incompatible with the selected environment."""

    def __init__(
        self,
        provider: str,
        environment: str,
    ) -> None:
        self.provider = provider
        self.environment = environment

        super().__init__(
            "Execution Provider is not supported by the selected environment: "
            f"provider={provider!r}, environment={environment!r}"
        )
