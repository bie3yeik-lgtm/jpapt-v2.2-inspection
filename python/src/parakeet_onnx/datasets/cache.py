"""
Resolved dataset selection cache.

This cache stores only deterministic resolution metadata.

It does NOT replace Hugging Face's own dataset/download cache and does not
copy the complete dataset into a project-specific representation.

Typical path:

    .cache/evaluation/manifests/<cache-key>.json

The cache is disposable. datasets-lock.json + manifest remain authoritative.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any

from .errors import DatasetCacheError
from .models import ResolvedDatasetSample, ResolvedManifest


@dataclass(frozen=True, slots=True)
class DatasetCacheEntry:
    key: str
    path: Path


def _canonical_json(
    value: Any,
) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _atomic_write(
    path: Path,
    content: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )

    temporary = Path(
        temporary_name
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as file:
            file.write(content)
            file.flush()
            os.fsync(
                file.fileno()
            )

        os.replace(
            temporary,
            path,
        )

    finally:
        if temporary.exists():
            temporary.unlink()


class DatasetCache:
    """
    Disposable deterministic manifest-resolution cache.
    """

    CACHE_SCHEMA_VERSION = 1

    def __init__(
        self,
        root: str | Path,
    ) -> None:
        self.root = (
            Path(root)
            .expanduser()
            .resolve()
        )

        self.manifest_root = (
            self.root
            / "manifests"
        )

    @staticmethod
    def make_key(
        *,
        manifest_bytes: bytes,
        datasets_lock_sha256: str,
    ) -> str:
        """
        Build a cache key entirely from authoritative inputs.
        """

        if not datasets_lock_sha256:
            raise DatasetCacheError(
                "datasets_lock_sha256 must not be empty."
            )

        digest = hashlib.sha256()

        digest.update(
            b"parakeet-onnx-resolved-manifest-v1\n"
        )

        digest.update(
            datasets_lock_sha256.encode(
                "ascii"
            )
        )

        digest.update(b"\n")

        digest.update(
            hashlib.sha256(
                manifest_bytes
            ).hexdigest().encode(
                "ascii"
            )
        )

        return digest.hexdigest()

    def entry(
        self,
        key: str,
    ) -> DatasetCacheEntry:
        if not key:
            raise DatasetCacheError(
                "Cache key must not be empty."
            )

        return DatasetCacheEntry(
            key=key,
            path=(
                self.manifest_root
                / f"{key}.json"
            ),
        )

    def load(
        self,
        key: str,
    ) -> ResolvedManifest | None:
        entry = self.entry(key)

        if not entry.path.is_file():
            return None

        try:
            raw = json.loads(
                entry.path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise DatasetCacheError(
                f"Invalid dataset cache entry: "
                f"{entry.path}: {exc}"
            ) from exc

        try:
            return self._decode(
                raw
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise DatasetCacheError(
                f"Dataset cache entry does not match "
                f"the expected schema: {entry.path}: {exc}"
            ) from exc

    def store(
        self,
        key: str,
        resolved: ResolvedManifest,
    ) -> DatasetCacheEntry:
        entry = self.entry(key)

        payload = {
            "cache_schema_version": (
                self.CACHE_SCHEMA_VERSION
            ),
            "key": key,
            "resolved_manifest": (
                resolved.to_dict()
            ),
        }

        _atomic_write(
            entry.path,
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

        return entry

    def remove(
        self,
        key: str,
    ) -> bool:
        entry = self.entry(key)

        if not entry.path.exists():
            return False

        entry.path.unlink()

        return True

    @staticmethod
    def _decode(
        raw: dict[str, Any],
    ) -> ResolvedManifest:
        version = raw[
            "cache_schema_version"
        ]

        if version != 1:
            raise ValueError(
                f"Unsupported cache schema version: {version}"
            )

        manifest = raw[
            "resolved_manifest"
        ]

        samples = tuple(
            ResolvedDatasetSample(
                id=item["id"],
                manifest_entry_id=item[
                    "manifest_entry_id"
                ],
                dataset_id=item[
                    "dataset_id"
                ],
                dataset_repo_id=item[
                    "dataset_repo_id"
                ],
                dataset_revision=item[
                    "dataset_revision"
                ],
                subset=item["subset"],
                split=item["split"],
                row_index=int(
                    item["row_index"]
                ),
                source_identity=item[
                    "source_identity"
                ],
                selection_hash=item[
                    "selection_hash"
                ],
                selection_rank=int(
                    item["selection_rank"]
                ),
                duration_sec=float(
                    item["duration_sec"]
                ),
                sample_rate_hz=(
                    int(
                        item[
                            "sample_rate_hz"
                        ]
                    )
                    if item[
                        "sample_rate_hz"
                    ]
                    is not None
                    else None
                ),
                transcription=item[
                    "transcription"
                ],
                tags=tuple(
                    item["tags"]
                ),
                audio_path=item[
                    "audio_path"
                ],
                audio_sha256=item[
                    "audio_sha256"
                ],
            )
            for item in manifest[
                "samples"
            ]
        )

        result = ResolvedManifest(
            schema_version=int(
                manifest[
                    "schema_version"
                ]
            ),
            manifest_path=manifest[
                "manifest_path"
            ],
            expected_sample_count=int(
                manifest[
                    "expected_sample_count"
                ]
            ),
            resolved_sample_count=int(
                manifest[
                    "resolved_sample_count"
                ]
            ),
            samples=samples,
        )

        result.validate()

        return result
