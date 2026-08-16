from __future__ import annotations

import pytest

from parakeet_onnx.evaluation import (
    compare_capsule_metric,
    summarize_experiment_capsule,
    summarize_experiment_capsules,
    write_capsule_row_batches,
)
from parakeet_onnx.evaluation.parquet import build_experiment_capsule_rows


def _write_capsule(path, run_id: str, cer: float, rtf: float) -> None:
    rows = build_experiment_capsule_rows(
        run_context={"run_id": run_id, "provider_id": "cpu"},
        samples=[],
        benchmark={
            "run_id": run_id,
            "samples": {"attempted": 0},
            "quality": {"cer": cer},
            "performance": {"rtf": rtf},
        },
    )
    write_capsule_row_batches(
        path,
        run_id=run_id,
        batches=(rows,),
    )


def test_summarize_and_compare_capsules(tmp_path) -> None:
    first = tmp_path / "run-a.parquet"
    second = tmp_path / "run-b.parquet"
    _write_capsule(first, "run-a", 0.10, 0.30)
    _write_capsule(second, "run-b", 0.05, 0.45)

    summaries = summarize_experiment_capsules([first, second])

    assert [summary.run_id for summary in summaries] == ["run-a", "run-b"]
    assert summaries[0].sample_count == 0
    assert summaries[0].artifact_count == 0
    assert summaries[0].diagnostic_count == 0
    assert summaries[0].metric("quality.cer") == pytest.approx(0.10)

    cer_best = compare_capsule_metric(summaries, "quality.cer").best()
    rtf_best = compare_capsule_metric(summaries, "performance.rtf").best()

    assert cer_best is not None
    assert cer_best[0] == "run-b"
    assert cer_best[1] == pytest.approx(0.05)
    assert rtf_best is not None
    assert rtf_best[0] == "run-a"
    assert rtf_best[1] == pytest.approx(0.30)


def test_single_capsule_summary_uses_projection(tmp_path) -> None:
    path = tmp_path / "run.parquet"
    _write_capsule(path, "run-projected", 0.25, 0.50)

    summary = summarize_experiment_capsule(path)

    assert summary.run_id == "run-projected"
    assert set(summary.metrics) == {
        "performance.rtf",
        "quality.cer",
        "samples.attempted",
    }
    assert summary.metrics["performance.rtf"] == pytest.approx(0.50)
    assert summary.metrics["quality.cer"] == pytest.approx(0.25)
    assert summary.metrics["samples.attempted"] == pytest.approx(0.0)
