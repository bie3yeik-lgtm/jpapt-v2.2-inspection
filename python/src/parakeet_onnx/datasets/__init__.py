"""
Dataset manifest resolution.

This package converts:

    evaluation/manifests/*.jsonl
        +
    HF Bucket config/revisions/datasets-lock.json
        +
    a pinned dataset snapshot

into a deterministic ordered set of evaluation samples.

The module is intentionally independent of ASR model/runtime code.
"""

from .cache import (
    DatasetCache,
    DatasetCacheEntry,
)
from .errors import (
    DatasetCacheError,
    DatasetError,
    DatasetManifestError,
    DatasetResolutionError,
)
from .manifest import (
    ManifestLoader,
    stable_hash,
    stable_hash_bytes,
)
from .materializer import (
    DatasetMaterializationError,
    DatasetMaterializer,
    MaterializedAudio,
)
from .models import (
    DatasetRecord,
    ManifestEntry,
    ManifestFilters,
    ManifestSelection,
    ResolvedDatasetSample,
    ResolvedManifest,
)
from .resolver import (
    DatasetBackend,
    DatasetResolver,
    HuggingFaceDatasetBackend,
)

__all__ = [
    "DatasetBackend",
    "DatasetCache",
    "DatasetCacheEntry",
    "DatasetCacheError",
    "DatasetError",
    "DatasetManifestError",
    "DatasetRecord",
    "DatasetResolutionError",
    "DatasetResolver",
    "HuggingFaceDatasetBackend",
    "ManifestEntry",
    "ManifestFilters",
    "ManifestLoader",
    "ManifestSelection",
    "ResolvedDatasetSample",
    "ResolvedManifest",
    "stable_hash",
    "stable_hash_bytes",
    "DatasetMaterializationError",
    "DatasetMaterializer",
    "MaterializedAudio",
]
