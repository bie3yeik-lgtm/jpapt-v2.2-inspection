"""
Low-level TOML loading utilities.

The loader performs only structural validation. Semantic validation belongs
to typed configuration classes and ConfigResolver.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .errors import (
    ConfigFileNotFoundError,
    ConfigValidationError,
)

ConfigDict = dict[str, Any]


def load_toml(
    path: str | Path,
    *,
    require_schema_version: bool = True,
) -> ConfigDict:
    """
    Load a TOML configuration file.

    Args:
        path:
            TOML file path.
        require_schema_version:
            Require the top-level ``schema_version`` field.

    Returns:
        Parsed TOML dictionary.

    Raises:
        ConfigFileNotFoundError:
            File does not exist.

        ConfigValidationError:
            TOML is malformed or required metadata is absent.
    """

    config_path = Path(path)

    if not config_path.is_file():
        raise ConfigFileNotFoundError(config_path)

    try:
        with config_path.open("rb") as file:
            data = tomllib.load(file)

    except tomllib.TOMLDecodeError as exc:
        raise ConfigValidationError(
            f"Invalid TOML: {exc}",
            path=config_path,
        ) from exc

    if not isinstance(data, dict):
        raise ConfigValidationError(
            "TOML root must be a table.",
            path=config_path,
        )

    if require_schema_version:
        schema_version = data.get("schema_version")

        if schema_version is None:
            raise ConfigValidationError(
                "Missing required top-level field: schema_version",
                path=config_path,
            )

        if not isinstance(schema_version, int):
            raise ConfigValidationError(
                "schema_version must be an integer.",
                path=config_path,
            )

        if schema_version != 1:
            raise ConfigValidationError(
                f"Unsupported schema_version: {schema_version}. Expected schema_version = 1.",
                path=config_path,
            )

    return data
