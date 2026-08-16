from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping


class AllocationCatalogError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AllocationCatalog:
    path: Path
    catalog_id: str
    sha256: str
    prefixes: Mapping[str, str]

    @classmethod
    def load(cls, path: str | Path) -> "AllocationCatalog":
        resolved = Path(path).expanduser().resolve()
        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AllocationCatalogError(
                f"failed to load HF allocation catalog {resolved}: {exc}"
            ) from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise AllocationCatalogError(
                "HF allocation catalog must be a schema_version=1 object"
            )
        catalog_id = raw.get("catalog_id")
        if not isinstance(catalog_id, str) or not catalog_id.strip():
            raise AllocationCatalogError("catalog_id must be a non-empty string")
        prefixes_raw = raw.get("prefixes")
        if not isinstance(prefixes_raw, dict) or not prefixes_raw:
            raise AllocationCatalogError("prefixes must be a non-empty object")
        prefixes: dict[str, str] = {}
        for key, value in prefixes_raw.items():
            if not isinstance(key, str) or not key.strip():
                raise AllocationCatalogError("prefix keys must be non-empty strings")
            if not isinstance(value, str) or not value.strip():
                raise AllocationCatalogError(
                    f"prefixes.{key} must be a non-empty string"
                )
            prefixes[key.strip()] = value.strip()
        canonical = json.dumps(
            raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return cls(
            path=resolved,
            catalog_id=catalog_id.strip(),
            sha256=hashlib.sha256(canonical).hexdigest(),
            prefixes=prefixes,
        )

    def prefix(self, key: str) -> str:
        try:
            return self.prefixes[key]
        except KeyError as exc:
            raise AllocationCatalogError(
                f"unknown allocation prefix key {key!r}; available={sorted(self.prefixes)}"
            ) from exc

    def candidate_prefix_key(self, profile_set_id: str) -> str:
        key = f"candidate.{profile_set_id}"
        if key in self.prefixes:
            return key
        return "candidate.default"


def load_repository_allocation_catalog(
    repository_root: str | Path,
) -> AllocationCatalog:
    return AllocationCatalog.load(
        Path(repository_root) / "config" / "hf-allocation-catalog.json"
    )
