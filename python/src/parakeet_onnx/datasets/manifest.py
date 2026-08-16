"""Minimal evaluation manifest loading and deterministic stable-hash selection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from parakeet_onnx.config.paths import RepositoryPaths

from .errors import DatasetManifestError
from .models import ManifestEntry, ManifestFilters, ManifestSelection


def stable_hash_bytes(
    *, dataset_revision: str, sample_identity: str, seed: str
) -> bytes:
    if not dataset_revision:
        raise ValueError("dataset_revision must not be empty.")
    if not sample_identity:
        raise ValueError("sample_identity must not be empty.")
    if not seed:
        raise ValueError("seed must not be empty.")
    key = f"{dataset_revision}\n{sample_identity}\n{seed}".encode("utf-8")
    return hashlib.sha256(key).digest()


def stable_hash(*, dataset_revision: str, sample_identity: str, seed: str) -> str:
    return stable_hash_bytes(
        dataset_revision=dataset_revision,
        sample_identity=sample_identity,
        seed=seed,
    ).hex()


class ManifestLoader:
    """Load minimal evaluation/manifests/*.jsonl into rich internal entries."""

    def __init__(self, repository_root: str | Path | None = None) -> None:
        if repository_root is None:
            self.paths = RepositoryPaths.discover()
        else:
            self.paths = RepositoryPaths(root=Path(repository_root).expanduser().resolve())
        schema_path = self.paths.root / "evaluation" / "schemas" / "manifest.schema.json"
        if not schema_path.is_file():
            raise DatasetManifestError("Manifest JSON Schema does not exist.", path=schema_path)
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DatasetManifestError(
                f"Invalid manifest JSON Schema: {exc}", path=schema_path
            ) from exc
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(schema)

    def load(self, path: str | Path) -> tuple[ManifestEntry, ...]:
        manifest_path = Path(path)
        if not manifest_path.is_absolute():
            manifest_path = self.paths.root / manifest_path
        manifest_path = manifest_path.resolve()
        if not manifest_path.is_file():
            raise DatasetManifestError("Manifest does not exist.", path=manifest_path)

        entries: list[ManifestEntry] = []
        with manifest_path.open("r", encoding="utf-8") as file:
            for line_number, raw_line in enumerate(file, start=1):
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
                    key=lambda error: list(error.absolute_path),
                )
                if errors:
                    raise DatasetManifestError(
                        f"Manifest schema violation: {errors[0].message}",
                        path=manifest_path,
                        line_number=line_number,
                    )
                try:
                    entry = self._parse_entry(raw, line_number=line_number)
                    entry.validate()
                except (TypeError, ValueError, KeyError) as exc:
                    raise DatasetManifestError(
                        str(exc), path=manifest_path, line_number=line_number
                    ) from exc
                entries.append(entry)

        if not entries:
            raise DatasetManifestError("Manifest contains no entries.", path=manifest_path)
        return tuple(entries)

    @staticmethod
    def expected_sample_count(entries: tuple[ManifestEntry, ...]) -> int:
        return sum(entry.selection.count for entry in entries)

    @staticmethod
    def _parse_entry(raw: dict[str, Any], *, line_number: int) -> ManifestEntry:
        dataset_id = str(raw["dataset_id"])
        # Human-authored IDs are unnecessary. The logical entry identity is
        # deterministic within the manifest and remains readable in results.
        entry_id = f"{dataset_id}-{line_number:03d}"
        return ManifestEntry(
            id=entry_id,
            dataset_id=dataset_id,
            selection=ManifestSelection(
                count=int(raw["count"]),
                seed=str(raw["seed"]),
            ),
            filters=ManifestFilters(
                min_duration_sec=(
                    float(raw["min_duration_sec"])
                    if raw.get("min_duration_sec") is not None
                    else None
                ),
                max_duration_sec=(
                    float(raw["max_duration_sec"])
                    if raw.get("max_duration_sec") is not None
                    else None
                ),
            ),
        )
