"""
Evaluation manifest loading and deterministic stable-hash selection.

Stable-hash specification
=========================

For each candidate dataset record:

    key =
        dataset_revision
        + "\\n"
        + sample_identity
        + "\\n"
        + seed

The key is encoded as UTF-8 and hashed using SHA-256.

Candidates are ordered by the 256-bit digest interpreted lexicographically
as raw bytes, which is equivalent to ascending unsigned big-endian integer
order.

This specification must remain identical in the future Rust implementation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from parakeet_onnx.config.paths import RepositoryPaths

from .errors import DatasetManifestError
from .models import (
    ManifestEntry,
    ManifestFilters,
    ManifestSelection,
)


def stable_hash_bytes(
    *,
    dataset_revision: str,
    sample_identity: str,
    seed: str,
) -> bytes:
    if not dataset_revision:
        raise ValueError(
            "dataset_revision must not be empty."
        )

    if not sample_identity:
        raise ValueError(
            "sample_identity must not be empty."
        )

    if not seed:
        raise ValueError(
            "seed must not be empty."
        )

    key = (
        f"{dataset_revision}\n"
        f"{sample_identity}\n"
        f"{seed}"
    ).encode("utf-8")

    return hashlib.sha256(key).digest()


def stable_hash(
    *,
    dataset_revision: str,
    sample_identity: str,
    seed: str,
) -> str:
    """
    Return the canonical lowercase hexadecimal stable hash.
    """

    return stable_hash_bytes(
        dataset_revision=dataset_revision,
        sample_identity=sample_identity,
        seed=seed,
    ).hex()


class ManifestLoader:
    """
    Load and validate evaluation/manifests/*.jsonl.
    """

    def __init__(
        self,
        repository_root: str | Path | None = None,
    ) -> None:
        if repository_root is None:
            self.paths = RepositoryPaths.discover()
        else:
            self.paths = RepositoryPaths(
                root=Path(repository_root).expanduser().resolve()
            )

        schema_path = (
            self.paths.root
            / "evaluation"
            / "schemas"
            / "manifest.schema.json"
        )

        if not schema_path.is_file():
            raise DatasetManifestError(
                "Manifest JSON Schema does not exist.",
                path=schema_path,
            )

        try:
            schema = json.loads(
                schema_path.read_text(
                    encoding="utf-8"
                )
            )
        except json.JSONDecodeError as exc:
            raise DatasetManifestError(
                f"Invalid manifest JSON Schema: {exc}",
                path=schema_path,
            ) from exc

        Draft202012Validator.check_schema(schema)

        self._validator = Draft202012Validator(
            schema
        )

    def load(
        self,
        path: str | Path,
    ) -> tuple[ManifestEntry, ...]:
        manifest_path = Path(path)

        if not manifest_path.is_absolute():
            manifest_path = (
                self.paths.root
                / manifest_path
            )

        manifest_path = manifest_path.resolve()

        if not manifest_path.is_file():
            raise DatasetManifestError(
                "Manifest does not exist.",
                path=manifest_path,
            )

        entries: list[ManifestEntry] = []

        with manifest_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            for line_number, raw_line in enumerate(
                file,
                start=1,
            ):
                line = raw_line.strip()

                if not line:
                    continue

                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DatasetManifestError(
                        f"Invalid JSON: {exc}",
                        path=manifest_path,
                        line_number=line_number,
                    ) from exc

                errors = sorted(
                    self._validator.iter_errors(raw),
                    key=lambda error: list(
                        error.absolute_path
                    ),
                )

                if errors:
                    first = errors[0]

                    raise DatasetManifestError(
                        f"Manifest schema violation: "
                        f"{first.message}",
                        path=manifest_path,
                        line_number=line_number,
                    )

                try:
                    entry = self._parse_entry(raw)
                    entry.validate()
                except (
                    TypeError,
                    ValueError,
                    KeyError,
                ) as exc:
                    raise DatasetManifestError(
                        str(exc),
                        path=manifest_path,
                        line_number=line_number,
                    ) from exc

                entries.append(entry)

        if not entries:
            raise DatasetManifestError(
                "Manifest contains no entries.",
                path=manifest_path,
            )

        ids = [
            entry.id
            for entry in entries
        ]

        if len(ids) != len(set(ids)):
            raise DatasetManifestError(
                "Manifest entry IDs must be unique.",
                path=manifest_path,
            )

        return tuple(entries)

    @staticmethod
    def expected_sample_count(
        entries: tuple[ManifestEntry, ...],
    ) -> int:
        return sum(
            entry.selection.count
            for entry in entries
        )

    @staticmethod
    def _parse_entry(
        raw: dict[str, Any],
    ) -> ManifestEntry:
        selection_raw = raw["selection"]
        filters_raw = raw["filters"]

        return ManifestEntry(
            schema_version=int(
                raw["schema_version"]
            ),
            id=str(raw["id"]),
            dataset_id=str(
                raw["dataset_id"]
            ),
            selection=ManifestSelection(
                strategy=selection_raw[
                    "strategy"
                ],
                count=int(
                    selection_raw["count"]
                ),
                seed=str(
                    selection_raw["seed"]
                ),
            ),
            filters=ManifestFilters(
                min_duration_sec=float(
                    filters_raw[
                        "min_duration_sec"
                    ]
                ),
                max_duration_sec=float(
                    filters_raw[
                        "max_duration_sec"
                    ]
                ),
            ),
            tags=tuple(
                str(tag)
                for tag in raw["tags"]
            ),
        )
