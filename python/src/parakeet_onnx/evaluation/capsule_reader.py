"""Reader and structural/integrity validator for ExperimentCapsuleV1."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .parquet import _CAPSULE_COLUMNS, EXPERIMENT_CAPSULE_SCHEMA_VERSION

_ALLOWED_RECORD_KINDS = frozenset({"manifest", "sample", "metric", "artifact", "diagnostic"})
_ALLOWED_DIAGNOSTIC_STATUSES = frozenset({"info", "warning", "error"})


class ExperimentCapsuleError(RuntimeError):
    """Raised when a Parquet capsule violates its contract."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_json_object(*, label: str, raw: Any, required: bool) -> dict[str, Any]:
    if raw is None or raw == "":
        if required:
            raise ExperimentCapsuleError(f"{label} is missing")
        return {}
    if not isinstance(raw, str):
        raise ExperimentCapsuleError(f"{label} must be a JSON string")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExperimentCapsuleError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ExperimentCapsuleError(f"{label} must decode to an object")
    return value


@dataclass(frozen=True, slots=True)
class ExperimentCapsule:
    path: Path
    run_id: str
    rows: tuple[Mapping[str, Any], ...]
    manifest: Mapping[str, Any]

    @property
    def samples(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.rows if row["record_kind"] == "sample")

    @property
    def metrics(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.rows if row["record_kind"] == "metric")

    @property
    def artifacts(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.rows if row["record_kind"] == "artifact")

    @property
    def diagnostics(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.rows if row["record_kind"] == "diagnostic")

    def metric(self, name: str) -> float | None:
        matches = [row for row in self.metrics if row.get("metric_name") == name]
        if not matches:
            return None
        if len(matches) != 1:
            raise ExperimentCapsuleError(f"metric {name!r} appears {len(matches)} times")
        value = matches[0].get("metric_value")
        return None if value is None else float(value)

    def manifest_metadata(self) -> dict[str, Any]:
        return _decode_json_object(
            label="manifest metadata_json",
            raw=self.manifest.get("metadata_json"),
            required=True,
        )

    def diagnostic_metadata(self, index: int) -> dict[str, Any]:
        try:
            row = self.diagnostics[index]
        except IndexError as exc:
            raise ExperimentCapsuleError(f"diagnostic index out of range: {index}") from exc
        return _decode_json_object(
            label=f"diagnostic {index} metadata_json",
            raw=row.get("metadata_json"),
            required=False,
        )

    def artifact_ids(self) -> tuple[str, ...]:
        return tuple(sorted({str(row["artifact_id"]) for row in self.artifacts}))

    def artifact_metadata(self, artifact_id: str) -> dict[str, Any]:
        rows = [row for row in self.artifacts if row.get("artifact_id") == artifact_id]
        if not rows:
            raise ExperimentCapsuleError(f"artifact not found: {artifact_id}")
        return _decode_json_object(
            label=f"artifact {artifact_id!r} metadata_json",
            raw=rows[0].get("metadata_json"),
            required=False,
        )

    def extract_artifact(self, artifact_id: str, output: str | Path) -> Path:
        rows = [row for row in self.artifacts if row.get("artifact_id") == artifact_id]
        if not rows:
            raise ExperimentCapsuleError(f"artifact not found: {artifact_id}")
        rows.sort(key=lambda row: int(row["artifact_part_index"]))

        metadata = self.artifact_metadata(artifact_id)
        if metadata.get("location") == "external":
            raise ExperimentCapsuleError(f"artifact {artifact_id!r} is external and has no embedded payload")

        payload = b"".join(bytes(row.get("payload") or b"") for row in rows)
        expected_size = rows[0].get("artifact_size_raw")
        expected_sha256 = rows[0].get("artifact_sha256")
        if len(payload) != expected_size:
            raise ExperimentCapsuleError(
                f"artifact {artifact_id!r} size mismatch: expected={expected_size}, actual={len(payload)}"
            )
        if _sha256(payload) != expected_sha256:
            raise ExperimentCapsuleError(f"artifact {artifact_id!r} SHA-256 mismatch")

        destination = Path(output).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination


def _load_rows(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        from datasets import Dataset
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Parquet capsule reading requires the project's 'datasets' optional dependency.") from exc
    dataset = Dataset.from_parquet(str(path))
    return list(dataset.column_names), [dict(row) for row in dataset]


def _require_nonempty_string(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ExperimentCapsuleError(f"{name} must be a non-empty string")
    return value


def _validate_artifact_rows(rows: list[dict[str, Any]]) -> None:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        artifact_id = _require_nonempty_string("artifact.artifact_id", row.get("artifact_id"))
        groups.setdefault(artifact_id, []).append(row)

    for artifact_id, parts in groups.items():
        parts.sort(key=lambda row: int(row.get("artifact_part_index") or 0))
        expected_count = parts[0].get("artifact_part_count")
        if not isinstance(expected_count, int) or expected_count <= 0:
            raise ExperimentCapsuleError(f"artifact {artifact_id!r} has invalid artifact_part_count")
        if len(parts) != expected_count:
            raise ExperimentCapsuleError(
                f"artifact {artifact_id!r} part count mismatch: expected={expected_count}, actual={len(parts)}"
            )
        common = (
            parts[0].get("artifact_name"),
            parts[0].get("mime_type"),
            parts[0].get("artifact_sha256"),
            parts[0].get("artifact_size_raw"),
        )
        offset = 0
        embedded = False
        for index, part in enumerate(parts):
            if part.get("artifact_part_index") != index:
                raise ExperimentCapsuleError(f"artifact {artifact_id!r} has non-contiguous part indexes")
            if part.get("artifact_offset") != offset:
                raise ExperimentCapsuleError(f"artifact {artifact_id!r} has invalid part offset at index {index}")
            if (
                part.get("artifact_name"),
                part.get("mime_type"),
                part.get("artifact_sha256"),
                part.get("artifact_size_raw"),
            ) != common:
                raise ExperimentCapsuleError(f"artifact {artifact_id!r} metadata differs across parts")
            payload = part.get("payload")
            if payload is not None:
                embedded = True
                payload_bytes = bytes(payload)
                if _sha256(payload_bytes) != part.get("artifact_part_sha256"):
                    raise ExperimentCapsuleError(f"artifact {artifact_id!r} part {index} SHA-256 mismatch")
                offset += len(payload_bytes)
        if embedded:
            payload = b"".join(bytes(part.get("payload") or b"") for part in parts)
            if len(payload) != common[3] or _sha256(payload) != common[2]:
                raise ExperimentCapsuleError(f"artifact {artifact_id!r} aggregate integrity check failed")


def _validate_diagnostic_rows(rows: list[dict[str, Any]]) -> None:
    for index, row in enumerate(rows):
        _require_nonempty_string(f"diagnostic {index}.name", row.get("name"))
        _require_nonempty_string(f"diagnostic {index}.category", row.get("category"))
        status = _require_nonempty_string(
            f"diagnostic {index}.status",
            row.get("status"),
        )
        if status not in _ALLOWED_DIAGNOSTIC_STATUSES:
            raise ExperimentCapsuleError(f"diagnostic {index}.status is unsupported: {status!r}")
        _decode_json_object(
            label=f"diagnostic {index} metadata_json",
            raw=row.get("metadata_json"),
            required=False,
        )


def _validate_rows(
    path: Path,
    columns: Iterable[str],
    rows: list[dict[str, Any]],
) -> ExperimentCapsule:
    actual_columns = tuple(columns)
    if actual_columns != _CAPSULE_COLUMNS:
        missing = sorted(set(_CAPSULE_COLUMNS) - set(actual_columns))
        extra = sorted(set(actual_columns) - set(_CAPSULE_COLUMNS))
        raise ExperimentCapsuleError(
            f"capsule columns do not match ExperimentCapsuleV1: missing={missing}, extra={extra}"
        )
    if not rows:
        raise ExperimentCapsuleError("capsule contains no rows")

    run_ids: set[str] = set()
    ordinals: list[int] = []
    manifests: list[dict[str, Any]] = []
    sample_ids: set[str] = set()

    for index, row in enumerate(rows):
        if row.get("schema_version") != EXPERIMENT_CAPSULE_SCHEMA_VERSION:
            raise ExperimentCapsuleError(f"row {index} has unsupported schema_version {row.get('schema_version')!r}")
        run_id = _require_nonempty_string(f"row {index}.run_id", row.get("run_id"))
        run_ids.add(run_id)
        record_kind = _require_nonempty_string(f"row {index}.record_kind", row.get("record_kind"))
        if record_kind not in _ALLOWED_RECORD_KINDS:
            raise ExperimentCapsuleError(f"row {index} has unsupported record_kind {record_kind!r}")
        ordinal = row.get("ordinal")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
            raise ExperimentCapsuleError(f"row {index}.ordinal must be a non-negative integer")
        ordinals.append(ordinal)

        if record_kind == "manifest":
            manifests.append(row)
        elif record_kind == "sample":
            sample_id = _require_nonempty_string(f"row {index}.sample_id", row.get("sample_id"))
            if sample_id in sample_ids:
                raise ExperimentCapsuleError(f"duplicate sample_id: {sample_id}")
            sample_ids.add(sample_id)
        elif record_kind == "metric":
            _require_nonempty_string(f"row {index}.metric_name", row.get("metric_name"))

    if len(run_ids) != 1:
        raise ExperimentCapsuleError(f"capsule contains multiple run IDs: {sorted(run_ids)}")
    if len(manifests) != 1:
        raise ExperimentCapsuleError(f"capsule must contain exactly one manifest row; found {len(manifests)}")
    if manifests[0].get("ordinal") != 0:
        raise ExperimentCapsuleError("manifest row must have ordinal 0")
    if ordinals != list(range(len(rows))):
        raise ExperimentCapsuleError("capsule ordinals must be contiguous and row-ordered")

    run_id = next(iter(run_ids))
    capsule = ExperimentCapsule(
        path=path,
        run_id=run_id,
        rows=tuple(rows),
        manifest=manifests[0],
    )
    metadata = capsule.manifest_metadata()
    run_context = metadata.get("run_context")
    benchmark = metadata.get("benchmark")
    if not isinstance(run_context, Mapping) or run_context.get("run_id") != run_id:
        raise ExperimentCapsuleError("manifest run_context.run_id does not match capsule run_id")
    if not isinstance(benchmark, Mapping) or benchmark.get("run_id") != run_id:
        raise ExperimentCapsuleError("manifest benchmark.run_id does not match capsule run_id")
    benchmark_samples = benchmark.get("samples")
    if (
        isinstance(benchmark_samples, Mapping)
        and isinstance(attempted := benchmark_samples.get("attempted"), int)
        and not isinstance(attempted, bool)
        and attempted != len(capsule.samples)
    ):
        raise ExperimentCapsuleError(
            "benchmark samples.attempted does not match Parquet sample rows: "
            f"benchmark={attempted}, parquet={len(capsule.samples)}"
        )

    _validate_artifact_rows([dict(row) for row in capsule.artifacts])
    _validate_diagnostic_rows([dict(row) for row in capsule.diagnostics])
    return capsule


def read_experiment_capsule(path: str | Path) -> ExperimentCapsule:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ExperimentCapsuleError(f"capsule does not exist: {resolved}")
    if resolved.stat().st_size <= 0:
        raise ExperimentCapsuleError(f"capsule is empty: {resolved}")
    columns, rows = _load_rows(resolved)
    return _validate_rows(resolved, columns, rows)


def validate_experiment_capsule(path: str | Path, *, expected_run_id: str | None = None) -> int:
    capsule = read_experiment_capsule(path)
    if expected_run_id is not None and capsule.run_id != expected_run_id:
        raise ExperimentCapsuleError(
            f"capsule run_id does not match expected run_id: capsule={capsule.run_id!r}, expected={expected_run_id!r}"
        )
    return len(capsule.samples)
