"""Strict run-context construction.

The Python runtime now uses the same non-null execution contract enforced by
Rust. Unknown identities are errors, not nullable placeholders.
"""

from parakeet_onnx.contracts import (
    ArtifactIdentity,
    ConfigSnapshot,
    ContractError,
    GitIdentity,
    HostIdentity,
    RunContext,
    RuntimeIdentity,
)
from .builder import RunContextBuilder, build_run_context
from .hashing import sha256_file

__all__ = [
    "ArtifactIdentity",
    "ConfigSnapshot",
    "ContractError",
    "GitIdentity",
    "HostIdentity",
    "RunContext",
    "RunContextBuilder",
    "RuntimeIdentity",
    "build_run_context",
    "sha256_file",
]
