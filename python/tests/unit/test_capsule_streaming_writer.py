from __future__ import annotations

import pyarrow.parquet as pq
import pytest

from parakeet_onnx.evaluation import (
    CAPSULE_PARQUET_COMPRESSION,
    CAPSULE_PARQUET_WRITER_VERSION,
    EXPERIMENT_CAPSULE_SCHEMA_VERSION,
    read_experiment_capsule,
    write_capsule_row_batches,
)
from parakeet_onnx.evaluation.parquet import build_experiment_capsule_rows


def _rows() -> list[dict[str, object]]:
    return build_experiment_capsule_rows(
        run_context={"run_id": "run-stream", "provider_id": "cpu"},
        samples=[],
        benchmark={
            "run_id": "run-stream",
            "samples": {"attempted": 0},
            "quality": {"cer": 0.0},
        },
    )


def test_streaming_writer_round_trips_and_sets_file_metadata(tmp_path) -> None:
    rows = _rows()
    path = tmp_path / "run.parquet"

    write_capsule_row_batches(
        path,
        run_id="run-stream",
        batches=(rows[:1], rows[1:]),
    )

    parquet_file = pq.ParquetFile(path)
    metadata = parquet_file.schema_arrow.metadata or {}

    assert metadata[b"jpapt.capsule.schema"].decode() == EXPERIMENT_CAPSULE_SCHEMA_VERSION
    assert metadata[b"jpapt.run_id"].decode() == "run-stream"
    assert metadata[b"jpapt.writer"].decode() == CAPSULE_PARQUET_WRITER_VERSION
    assert parquet_file.metadata.num_row_groups == 2
    assert parquet_file.metadata.row_group(0).column(0).compression.lower() == (
        CAPSULE_PARQUET_COMPRESSION
    )

    capsule = read_experiment_capsule(path)
    assert capsule.run_id == "run-stream"
    assert capsule.metric("quality.cer") == pytest.approx(0.0)


def test_streaming_writer_rejects_empty_row_stream_atomically(tmp_path) -> None:
    path = tmp_path / "run.parquet"

    with pytest.raises(ValueError, match="produced no rows"):
        write_capsule_row_batches(
            path,
            run_id="run-stream",
            batches=(),
        )

    assert not path.exists()
