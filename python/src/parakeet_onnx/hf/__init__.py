"""
Hugging Face integration helpers.

This package owns Hugging Face-specific concerns such as:

- HF Bucket revision locks
- HF Model Repository metadata
- candidate/reference/run artifact resolution

It must not own model inference logic.
"""

from .revisions import (
    DatasetLock,
    DatasetLockEntry,
    EvaluationSchemaRevision,
    ReferenceRevision,
    RevisionBundle,
    RevisionDocument,
    RevisionError,
    RevisionLoader,
)

__all__ = [
    "DatasetLock",
    "DatasetLockEntry",
    "EvaluationSchemaRevision",
    "ReferenceRevision",
    "RevisionBundle",
    "RevisionDocument",
    "RevisionError",
    "RevisionLoader",
]
