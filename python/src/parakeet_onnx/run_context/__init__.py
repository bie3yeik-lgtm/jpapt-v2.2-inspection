"""
Run-context generation.

A RunContext is the immutable identity and environment description of one
evaluation execution.

It combines:

- Git-managed ResolvedConfig
- HF Bucket revision locks
- candidate artifact digest
- Git commit
- runtime/provider/platform metadata

The serialized run-context.json is persisted with every evaluation run.
"""

from .builder import RunContextBuilder, build_run_context
from .hashing import sha256_file
from .models import (
    ArtifactIdentity,
    GitIdentity,
    HostIdentity,
    RunContext,
    RuntimeIdentity,
)

__all__ = [
    "ArtifactIdentity",
    "GitIdentity",
    "HostIdentity",
    "RunContext",
    "RunContextBuilder",
    "RuntimeIdentity",
    "build_run_context",
    "sha256_file",
]
