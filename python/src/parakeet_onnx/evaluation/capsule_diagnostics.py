"""Typed diagnostic records for ExperimentCapsuleV1.

Diagnostics are small structured observations about an evaluation run. They are
stored directly in the capsule and are intentionally distinct from large debug
artifacts, which use the artifact transport path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

_ALLOWED_DIAGNOSTIC_STATUSES = frozenset({"info", "warning", "error"})


class CapsuleDiagnosticError(ValueError):
    """Raised when a diagnostic violates the capsule contract."""


@dataclass(frozen=True, slots=True)
class CapsuleDiagnostic:
    """One small structured diagnostic observation.

    ``name`` is a stable machine-readable identifier, while ``category`` groups
    related observations such as provider, parity, frontend, runtime, or data.
    Large traces and profiles should be represented as capsule artifacts instead
    of being copied into ``metadata``.
    """

    name: str
    category: str
    status: str = "info"
    message: str | None = None
    code: str | None = None
    stage: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise CapsuleDiagnosticError("diagnostic name must be non-empty")
        if not self.category:
            raise CapsuleDiagnosticError("diagnostic category must be non-empty")
        if self.status not in _ALLOWED_DIAGNOSTIC_STATUSES:
            raise CapsuleDiagnosticError(
                f"diagnostic status must be one of {sorted(_ALLOWED_DIAGNOSTIC_STATUSES)}; got {self.status!r}"
            )
        if self.message is not None and not isinstance(self.message, str):
            raise CapsuleDiagnosticError("diagnostic message must be a string or None")
        if self.code is not None and not self.code:
            raise CapsuleDiagnosticError("diagnostic code must be non-empty when provided")
        if self.stage is not None and not self.stage:
            raise CapsuleDiagnosticError("diagnostic stage must be non-empty when provided")
        if not isinstance(self.metadata, Mapping):
            raise CapsuleDiagnosticError("diagnostic metadata must be a mapping")
