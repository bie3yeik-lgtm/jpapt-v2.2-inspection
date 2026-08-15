"""
Hugging Face integration helpers.

This package owns Hugging Face-specific concerns such as:

- HF Bucket revision locks
- static ASR development target profiles
- HF Model Repository metadata
- candidate/reference/run artifact resolution

It must not own model inference logic.
"""

from .revisions import (
    DatasetLock,
    DatasetLockEntry,
    DecoderRevisionSet,
    EvaluationSchemaRevision,
    ReferenceRevision,
    RevisionBundle,
    RevisionDocument,
    RevisionError,
    RevisionLoader,
)
from .targets import (
    HfTarget,
    HfTargetError,
    load_hf_target,
    load_hf_target_by_id,
)

__all__ = [
    "DatasetLock",
    "DatasetLockEntry",
    "DecoderRevisionSet",
    "EvaluationSchemaRevision",
    "HfTarget",
    "HfTargetError",
    "ReferenceRevision",
    "RevisionBundle",
    "RevisionDocument",
    "RevisionError",
    "RevisionLoader",
    "load_hf_target",
    "load_hf_target_by_id",
]
