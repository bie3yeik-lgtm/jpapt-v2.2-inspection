"""Reader and structural validator for ExperimentCapsuleV1 Parquet files."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .parquet import EXPERIMENT_CAPSULE_SCHEMA_VERSION, _CAPSULE_COLUMNS


_ALLOWED_RECORD_KINDS = frozenset({"manifest", "sample", "metric", "artifact"})


class ExperimentCapsuleError(RuntimeError):
    """Raised when a Parquet capsule violates the Phase-1/2 contract."""


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

    def metric(self, name: str) -> float | None:
        matches = [
            row
            for row in self.metrics
            if row.get("metric_name") == name
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise ExperimentCapsuleError(
                f"metric {name!r} appears {len(matches)} times"
            )
        value = matches[0].get("metric_value")
        return None if value is None else float(value)

    def manifest_metadata(self) -> dict[str, Any]:
        raw = self.manifest.get("metadata_json")
        if not isinstance(raw, str) or not raw:
            raise ExperimentCapsuleError("manifest metadata_json is missing")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExperimentCapsuleError(
                f"manifest metadata_json is invalid JSON: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise ExperimentCapsuleError("manifest metadata_json must decode to an object")
        return value


def _load_rows(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        from datasets import Dataset
    except ImportError as exc:  # pragma: no cover - environment contract failure
        raise RuntimeError(
            "Parquet capsule reading requires the project's 'datasets' optional dependency."
        ) from exc

    dataset = Dataset.from_parquet(str(path))
    return list(dataset.column_names), [dict(row) for row in dataset]


def _require_nonempty_string(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ExperimentCapsuleError(f"{name} must be a non-empty string")
    return value


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
            "capsule columns do not match ExperimentCapsuleV1: "
            f"missing={missing}, extra={extra}"
        )
    if not rows:
        raise ExperimentCapsuleError("capsule contains no rows")

    run_ids: set[str] = set()
    ordinals: list[int] = []
    manifests: list[dict[str, Any]] = []
    sample_ids: set[str] = set()

    for index, row in enumerate(rows):
        schema_version = row.get("schema_version")
        if schema_version != EXPERIMENT_CAPSULE_SCHEMA_VERSION:
            raise ExperimentCapsuleError(
                f"row {index} has unsupported schema_version {schema_version!r}"
            )

        run_id = _require_nonempty_string(f"row {index}.run_id", row.get("run_id"))
        run_ids.add(run_id)

        record_kind = _require_nonempty_string(
            f"row {index}.record_kind",
            row.get("record_kind"),
        )
        if record_kind not in _ALLOWED_RECORD_KINDS:
            raise ExperimentCapsuleError(
                f"row {index} has unsupported record_kind {record_kind!r}"
            )

        ordinal = row.get("ordinal")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
            raise ExperimentCapsuleError(
                f"row {index}.ordinal must be a non-negative integer"
            )
        ordinals.append(ordinal)

        if record_kind == "manifest":
            manifests.append(row)
        elif record_kind == "sample":
            sample_id = _require_nonempty_string(
                f"row {index}.sample_id",
                row.get("sample_id"),
            )
            if sample_id in sample_ids:
                raise ExperimentCapsuleError(f"duplicate sample_id: {sample_id}")
            sample_ids.add(sample_id)
        elif record_kind == "metric":
            _require_nonempty_string(
                f"row {index}.metric_name",
                row.get("metric_name"),
            )
        elif record_kind == "artifact":
            _require_nonempty_string(
                f"row {index}.artifact_id",
                row.get("artifact_id"),
            )

    if len(run_ids) != 1:
        raise ExperimentCapsuleError(
            f"capsule contains multiple run IDs: {sorted(run_ids)}"
        )
    if len(manifests) != 1:
        raise ExperimentCapsuleError(
            f"capsule must contain exactly one manifest row; found {len(manifests)}"
        )
    if manifests[0].get("ordinal") != 0:
        raise ExperimentCapsuleError("manifest row must have ordinal 0")

    expected_ordinals = list(range(len(rows)))
    if ordinals != expected_ordinals:
        raise ExperimentCapsuleError(
            "capsule ordinals must be contiguous and row-ordered: "
            f"expected={expected_ordinals}, actual={ordinals}"
        )

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
        raise ExperimentCapsuleError(
            "manifest run_context.run_id does not match capsule run_id"
        )
    if not isinstance(benchmark, Mapping) or benchmark.get("run_id") != run_id:
        raise ExperimentCapsuleError(
            "manifest benchmark.run_id does not match capsule run_id"
        )

    benchmark_samples = benchmark.get("samples")
    if isinstance(benchmark_samples, Mapping):
        attempted = benchmark_samples.get("attempted")
        if isinstance(attempted, int) and not isinstance(attempted, bool):
            if attempted != len(capsule.samples):
                raise ExperimentCapsuleError(
                    "benchmark samples.attempted does not match Parquet sample rows: "
                    f"benchmark={attempted}, parquet={len(capsule.samples)}"
                )

    return capsule


def read_experiment_capsule(path: str | Path) -> ExperimentCapsule:
    """Load and validate one ``run.parquet`` ExperimentCapsuleV1 file."""

    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ExperimentCapsuleError(f"capsule does not exist: {resolved}")
    if resolved.stat().st_size <= 0:
        raise ExperimentCapsuleError(f"capsule is empty: {resolved}")
    columns, rows = _load_rows(resolved)
    return _validate_rows(resolved, columns, rows)


def validate_experiment_capsule(path: str | Path, *, expected_run_id: str | None = None) -> int:
    """Validate a capsule and return the number of sample records."""

    capsule = read_experiment_capsule(path)
    if expected_run_id is not None and capsule.run_id != expected_run_id:
        raise ExperimentCapsuleError(
            "capsule run_id does not match expected run_id: "
            f"capsule={capsule.run_id!r}, expected={expected_run_id!r}"
        )
    return len(capsule.samples)
