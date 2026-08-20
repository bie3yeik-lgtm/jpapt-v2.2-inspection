from __future__ import annotations

import pytest

from parakeet_onnx.evaluation import (
    CapsuleDiagnostic,
    iter_experiment_capsule_row_batches,
    iter_experiment_capsule_rows,
)
from parakeet_onnx.evaluation.parquet import build_experiment_capsule_rows


def _benchmark() -> dict[str, object]:
    return {
        "run_id": "run-001",
        "samples": {"attempted": 0},
        "quality": {"cer": 0.1, "wer": 0.2},
    }


def test_row_iterator_matches_materialized_compatibility_helper() -> None:
    kwargs = {
        "run_context": {"run_id": "run-001"},
        "samples": [],
        "benchmark": _benchmark(),
        "diagnostics": [
            CapsuleDiagnostic(name="runtime-note", category="runtime"),
        ],
    }

    streamed = list(iter_experiment_capsule_rows(**kwargs))
    materialized = build_experiment_capsule_rows(**kwargs)

    assert streamed == materialized
    assert [row["ordinal"] for row in streamed] == list(range(len(streamed)))


def test_row_iterator_yields_manifest_before_consuming_samples() -> None:
    def samples():
        raise RuntimeError("samples were consumed")
        yield  # pragma: no cover

    rows = iter_experiment_capsule_rows(
        run_context={"run_id": "run-001"},
        samples=samples(),
        benchmark=_benchmark(),
    )

    first = next(rows)
    assert first["record_kind"] == "manifest"
    assert first["ordinal"] == 0

    with pytest.raises(RuntimeError, match="samples were consumed"):
        next(rows)


def test_row_batches_are_bounded_and_lossless() -> None:
    kwargs = {
        "run_context": {"run_id": "run-001"},
        "samples": [],
        "benchmark": _benchmark(),
        "diagnostics": [CapsuleDiagnostic(name=f"diagnostic-{index}", category="runtime") for index in range(5)],
    }

    rows = list(iter_experiment_capsule_rows(**kwargs))
    batches = list(iter_experiment_capsule_row_batches(**kwargs, batch_size=2))

    assert all(1 <= len(batch) <= 2 for batch in batches)
    assert [row for batch in batches for row in batch] == rows


def test_row_batches_reject_invalid_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        list(
            iter_experiment_capsule_row_batches(
                run_context={"run_id": "run-001"},
                samples=[],
                benchmark=_benchmark(),
                batch_size=0,
            )
        )
