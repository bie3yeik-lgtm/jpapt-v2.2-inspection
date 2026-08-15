"""
Dataset-specific exception hierarchy.
"""

from __future__ import annotations

from pathlib import Path


class DatasetError(RuntimeError):
    """Base class for dataset subsystem errors."""


class DatasetManifestError(DatasetError):
    """Raised when a manifest is syntactically or semantically invalid."""

    def __init__(
        self,
        message: str,
        *,
        path: str | Path | None = None,
        line_number: int | None = None,
    ) -> None:
        self.path = (
            Path(path)
            if path is not None
            else None
        )
        self.line_number = line_number

        details = [message]

        if self.path is not None:
            details.append(f"file={self.path}")

        if line_number is not None:
            details.append(f"line={line_number}")

        super().__init__("; ".join(details))


class DatasetResolutionError(DatasetError):
    """Raised when a locked manifest selection cannot be resolved."""


class DatasetCacheError(DatasetError):
    """Raised when persistent dataset cache state is invalid."""
