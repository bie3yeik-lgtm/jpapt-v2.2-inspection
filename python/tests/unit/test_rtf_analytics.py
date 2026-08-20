from __future__ import annotations

import pytest

from parakeet_onnx.evaluation.capsule_analytics import (
    RtfServiceRecord,
    rank_rtf_services,
)


def test_ranks_completed_records_deterministically() -> None:
    records = [
        RtfServiceRecord("run-b", "runpod-pod", "completed", 0.02, 50.0, 0.01),
        RtfServiceRecord("run-a", "hf-jobs", "completed", 0.01, 100.0, 0.02),
        RtfServiceRecord("run-c", "runpod-serverless", "blocked", None, None, None),
    ]
    ranked = rank_rtf_services(records)
    assert [record.run_id for record in ranked] == ["run-b", "run-a"]


def test_rejects_duplicate_run_ids_and_unknown_metric() -> None:
    record = RtfServiceRecord("run-a", "hf-jobs", "completed", 0.01, 100.0, 0.02)
    with pytest.raises(ValueError):
        rank_rtf_services([record, record])
    with pytest.raises(ValueError):
        rank_rtf_services([record], metric="gpu_utilization")
