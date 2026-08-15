"""
Execution environment detection.
"""

from __future__ import annotations

import os
import platform

from .errors import UnsupportedEnvironmentError


_ENVIRONMENT_OVERRIDE = "PARAKEET_ONNX_ENVIRONMENT"

SUPPORTED_ENVIRONMENTS = frozenset(
    {
        "linux",
        "windows",
        "macos",
    }
)


def normalize_environment_id(value: str) -> str:
    """
    Normalize environment aliases into project environment identifiers.
    """

    normalized = value.strip().lower()

    aliases = {
        "linux": "linux",
        "ubuntu": "linux",
        "wsl": "linux",
        "wsl2": "linux",
        "windows": "windows",
        "win": "windows",
        "win32": "windows",
        "mac": "macos",
        "macos": "macos",
        "darwin": "macos",
        "osx": "macos",
    }

    result = aliases.get(normalized)

    if result is None:
        raise UnsupportedEnvironmentError(value)

    return result


def detect_environment_id() -> str:
    """
    Detect the project execution environment.

    ``PARAKEET_ONNX_ENVIRONMENT`` may be used as an explicit override.

    WSL2 intentionally resolves to ``linux`` because Execution Provider and
    filesystem behavior are evaluated from the Linux process perspective.
    """

    override = os.environ.get(_ENVIRONMENT_OVERRIDE)

    if override:
        return normalize_environment_id(override)

    system = platform.system()

    mapping = {
        "Linux": "linux",
        "Windows": "windows",
        "Darwin": "macos",
    }

    environment_id = mapping.get(system)

    if environment_id is None:
        raise UnsupportedEnvironmentError(system)

    return environment_id


def is_wsl() -> bool:
    """
    Return True when running inside Windows Subsystem for Linux.

    This is metadata only. WSL still uses the ``linux`` environment config.
    """

    if platform.system() != "Linux":
        return False

    release = platform.release().lower()

    return (
        "microsoft" in release
        or "wsl" in release
    )
