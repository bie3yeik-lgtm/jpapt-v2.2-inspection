"""Projected cross-run analytics for ExperimentCapsuleV1 files."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .capsule_reader import ExperimentCapsuleError
from .parquet import EXPERIMENT_CAPSULE_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class CapsuleRunSummary:
    path: Path
    run_id: str
    sample_count: int
    diagnostic_count: int
    artifact_count: int
    metrics: Mapping[str, float]

    def metric(self, name: str) -> float | None:
        value = self.metrics.get(name)
        return None if value is None else float(value)


@dataclass(frozen=True, slots=True)
class CapsuleMetricComparison:
    metric_name: str
    values: tuple[tuple[str, float | None], ...]

    def best(self, *, lower_is_better: bool = True) -> tuple[str, float] | None:
        available = [(run_id, value) for run_id, value in self.values if value is not None]
        if not available:
            return None

        def key(item):
            return item[1]

        return min(available, key=key) if lower_is_better else max(available, key=key)


@dataclass(frozen=True, slots=True)
class RtfServiceRecord:
    """One normalized service benchmark observation."""

    run_id: str
    service_id: str
    status: str
    rtf: float | None
    rtfx: float | None
    cost_per_audio_hour: float | None


def rank_rtf_services(
    records: Iterable[RtfServiceRecord],
    *,
    metric: str = "cost_per_audio_hour",
) -> tuple[RtfServiceRecord, ...]:
    """Return deterministic ranking, excluding non-completed/unmeasured records."""

    if metric not in {"rtf", "cost_per_audio_hour"}:
        raise ValueError(f"Unsupported RTF ranking metric: {metric!r}")
    materialized = list(records)
    run_ids = [record.run_id for record in materialized]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("duplicate run_id in RTF service records")

    def value(record: RtfServiceRecord) -> float | None:
        candidate = getattr(record, metric)
        return candidate if candidate is not None else None

    ranked = [record for record in materialized if record.status == "completed" and value(record) is not None]
    return tuple(
        sorted(
            ranked,
            key=lambda record: (value(record), record.service_id, record.run_id),
        )
    )


def _pyarrow_parquet() -> object:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - environment contract failure
        raise RuntimeError(
            "Capsule analytics requires pyarrow from the project's locked 'datasets' optional dependency."
        ) from exc
    return pq


def _decode_metadata(metadata: Mapping[bytes, bytes] | None, key: bytes) -> str | None:
    if not metadata or key not in metadata:
        return None
    return metadata[key].decode("utf-8")


def summarize_experiment_capsule(path: str | Path) -> CapsuleRunSummary:
    """Read only analytical columns and summarize one capsule."""

    pq = _pyarrow_parquet()
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ExperimentCapsuleError(f"capsule does not exist or is empty: {resolved}")

    parquet_file = pq.ParquetFile(resolved)
    metadata = parquet_file.schema_arrow.metadata
    schema_version = _decode_metadata(metadata, b"jpapt.capsule.schema")
    run_id_from_metadata = _decode_metadata(metadata, b"jpapt.run_id")
    if schema_version is not None and schema_version != EXPERIMENT_CAPSULE_SCHEMA_VERSION:
        raise ExperimentCapsuleError(f"unsupported capsule schema metadata: {schema_version!r}")

    table = parquet_file.read(
        columns=[
            "run_id",
            "record_kind",
            "metric_name",
            "metric_value",
            "artifact_id",
        ]
    )
    values = table.to_pylist()
    if not values:
        raise ExperimentCapsuleError(f"capsule contains no rows: {resolved}")

    run_ids = {row["run_id"] for row in values if row.get("run_id")}
    if len(run_ids) != 1:
        raise ExperimentCapsuleError(f"capsule contains multiple run IDs: {sorted(run_ids)}")
    run_id = str(next(iter(run_ids)))
    if run_id_from_metadata is not None and run_id_from_metadata != run_id:
        raise ExperimentCapsuleError("Parquet file metadata run ID does not match analytical rows")

    sample_count = 0
    diagnostic_count = 0
    artifact_ids: set[str] = set()
    metrics: dict[str, float] = {}
    for row in values:
        kind = row.get("record_kind")
        if kind == "sample":
            sample_count += 1
        elif kind == "diagnostic":
            diagnostic_count += 1
        elif kind == "artifact":
            artifact_id = row.get("artifact_id")
            if artifact_id:
                artifact_ids.add(str(artifact_id))
        elif kind == "metric":
            name = row.get("metric_name")
            value = row.get("metric_value")
            if not isinstance(name, str) or not name:
                raise ExperimentCapsuleError("metric row has no metric_name")
            if name in metrics:
                raise ExperimentCapsuleError(f"duplicate metric in capsule: {name}")
            if value is not None:
                metrics[name] = float(value)

    return CapsuleRunSummary(
        path=resolved,
        run_id=run_id,
        sample_count=sample_count,
        diagnostic_count=diagnostic_count,
        artifact_count=len(artifact_ids),
        metrics=metrics,
    )


def summarize_experiment_capsules(
    paths: Iterable[str | Path],
) -> tuple[CapsuleRunSummary, ...]:
    """Summarize multiple capsules while rejecting duplicate run IDs."""

    summaries: list[CapsuleRunSummary] = []
    run_ids: set[str] = set()
    for path in paths:
        summary = summarize_experiment_capsule(path)
        if summary.run_id in run_ids:
            raise ExperimentCapsuleError(f"duplicate run_id across capsule set: {summary.run_id}")
        run_ids.add(summary.run_id)
        summaries.append(summary)
    return tuple(summaries)


def compare_capsule_metric(
    summaries: Iterable[CapsuleRunSummary],
    metric_name: str,
) -> CapsuleMetricComparison:
    """Create a stable run-by-run comparison for one metric."""

    if not isinstance(metric_name, str) or not metric_name:
        raise ValueError("metric_name must be a non-empty string")
    values = tuple((summary.run_id, summary.metric(metric_name)) for summary in summaries)
    return CapsuleMetricComparison(metric_name=metric_name, values=values)
