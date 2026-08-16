"""Bounded-memory PyArrow writer for ExperimentCapsuleV1."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

from parakeet_onnx.contracts import RunContext

from .capsule_artifacts import CapsuleArtifact
from .capsule_diagnostics import CapsuleDiagnostic
from .models import BenchmarkResult, SampleResult
from .parquet import (
    DEFAULT_CAPSULE_ROW_BATCH_SIZE,
    EXPERIMENT_CAPSULE_SCHEMA_VERSION,
    _CAPSULE_COLUMNS,
    iter_experiment_capsule_row_batches,
)

CAPSULE_PARQUET_COMPRESSION = "zstd"
CAPSULE_PARQUET_COMPRESSION_LEVEL = 3
CAPSULE_PARQUET_WRITER_VERSION = "python-pyarrow-streaming/v1"

_STRING_COLUMNS = {
    "schema_version",
    "run_id",
    "record_kind",
    "name",
    "category",
    "metadata_json",
    "sample_id",
    "dataset_id",
    "dataset_repo_id",
    "dataset_revision",
    "subset",
    "split",
    "audio_sha256",
    "reference_text",
    "hypothesis_text",
    "normalized_text",
    "provider_id",
    "decoder",
    "status",
    "error_code",
    "error_stage",
    "error_message",
    "metric_name",
    "metric_unit",
    "artifact_id",
    "artifact_name",
    "mime_type",
    "artifact_sha256",
    "artifact_part_sha256",
}
_FLOAT64_COLUMNS = {
    "audio_duration_sec",
    "cer",
    "wer",
    "load_ms",
    "session_creation_ms",
    "audio_decode_ms",
    "resample_ms",
    "frontend_ms",
    "encoder_ms",
    "inference_ms",
    "decoder_ms",
    "postprocess_ms",
    "total_ms",
    "rtf",
    "peak_ram_mb",
    "peak_device_memory_mb",
    "metric_value",
}
_INT32_COLUMNS = {
    "sample_rate_hz",
    "artifact_part_index",
    "artifact_part_count",
}
_INT64_COLUMNS = {
    "ordinal",
    "artifact_size_raw",
    "artifact_offset",
}


def _pyarrow_modules() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - environment contract failure
        raise RuntimeError(
            "Streaming Parquet output requires pyarrow from the project's "
            "locked 'datasets' optional dependency."
        ) from exc
    return pa, pq


def capsule_arrow_schema(*, run_id: str) -> Any:
    """Return the exact ExperimentCapsuleV1 Arrow schema plus file metadata."""

    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")

    pa, _ = _pyarrow_modules()
    fields = []
    for name in _CAPSULE_COLUMNS:
        if name in _STRING_COLUMNS:
            data_type = pa.string()
        elif name in _FLOAT64_COLUMNS:
            data_type = pa.float64()
        elif name in _INT32_COLUMNS:
            data_type = pa.int32()
        elif name in _INT64_COLUMNS:
            data_type = pa.int64()
        elif name == "payload":
            data_type = pa.binary()
        else:  # pragma: no cover - schema maintenance guard
            raise AssertionError(f"Arrow type is not defined for capsule column: {name}")

        fields.append(
            pa.field(
                name,
                data_type,
                nullable=name not in {"schema_version", "run_id", "record_kind", "ordinal"},
            )
        )

    return pa.schema(
        fields,
        metadata={
            b"jpapt.capsule.schema": EXPERIMENT_CAPSULE_SCHEMA_VERSION.encode("utf-8"),
            b"jpapt.run_id": run_id.encode("utf-8"),
            b"jpapt.writer": CAPSULE_PARQUET_WRITER_VERSION.encode("utf-8"),
        },
    )


def write_capsule_row_batches(
    destination: str | Path,
    *,
    run_id: str,
    batches: Iterable[Iterable[Mapping[str, Any]]],
) -> None:
    """Atomically stream bounded capsule batches into one Parquet file."""

    pa, pq = _pyarrow_modules()
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = capsule_arrow_schema(run_id=run_id)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(fd)
    temporary = Path(temporary_name)

    dictionary_columns = sorted(_STRING_COLUMNS)
    statistics_columns = [name for name in _CAPSULE_COLUMNS if name != "payload"]
    writer = None
    wrote_rows = False

    try:
        writer = pq.ParquetWriter(
            str(temporary),
            schema,
            compression=CAPSULE_PARQUET_COMPRESSION,
            compression_level=CAPSULE_PARQUET_COMPRESSION_LEVEL,
            use_dictionary=dictionary_columns,
            write_statistics=statistics_columns,
        )
        for batch in batches:
            rows = [dict(row) for row in batch]
            if not rows:
                continue
            table = pa.Table.from_pylist(rows, schema=schema)
            writer.write_table(table, row_group_size=len(rows))
            wrote_rows = True

        if not wrote_rows:
            raise ValueError("capsule row stream produced no rows")

        writer.close()
        writer = None
        os.replace(temporary, path)
    finally:
        if writer is not None:
            writer.close()
        if temporary.exists():
            temporary.unlink()


class StreamingExperimentCapsuleWriter:
    """Write ExperimentCapsuleV1 with bounded row materialization."""

    def __init__(
        self,
        path: str | Path,
        *,
        batch_size: int = DEFAULT_CAPSULE_ROW_BATCH_SIZE,
    ) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        self.path = Path(path)
        self.batch_size = batch_size

    def write(
        self,
        *,
        run_context: RunContext,
        samples: Iterable[SampleResult],
        benchmark: BenchmarkResult,
        artifacts: Iterable[CapsuleArtifact] = (),
        diagnostics: Iterable[CapsuleDiagnostic] = (),
    ) -> None:
        run_context_value = run_context.to_dict()
        run_id = run_context_value.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_context must contain a non-empty run_id")

        batches = iter_experiment_capsule_row_batches(
            run_context=run_context_value,
            samples=(sample.to_dict() for sample in samples),
            benchmark=benchmark.to_dict(),
            artifacts=artifacts,
            diagnostics=diagnostics,
            batch_size=self.batch_size,
        )
        write_capsule_row_batches(
            self.path,
            run_id=run_id,
            batches=batches,
        )
