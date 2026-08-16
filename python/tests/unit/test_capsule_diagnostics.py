from __future__ import annotations

import pytest

from parakeet_onnx.evaluation import (
    CapsuleDiagnostic,
    CapsuleDiagnosticError,
    read_experiment_capsule,
)
from parakeet_onnx.evaluation.parquet import (
    _atomic_write_parquet,
    build_experiment_capsule_rows,
)


def _benchmark() -> dict[str, object]:
    return {
        "run_id": "run-001",
        "samples": {"attempted": 0},
    }


def test_capsule_diagnostic_rejects_unknown_status() -> None:
    with pytest.raises(CapsuleDiagnosticError, match="status"):
        CapsuleDiagnostic(
            name="provider-fallback",
            category="provider",
            status="fatal",
        )


def test_diagnostic_round_trip(tmp_path) -> None:
    rows = build_experiment_capsule_rows(
        run_context={"run_id": "run-001"},
        samples=[],
        benchmark=_benchmark(),
        diagnostics=[
            CapsuleDiagnostic(
                name="provider-fallback",
                category="provider",
                status="warning",
                message="CPU fallback nodes were detected",
                code="ORT_PROVIDER_FALLBACK",
                stage="inference",
                metadata={
                    "assigned_nodes": 110,
                    "fallback_nodes": 3,
                },
            )
        ],
    )

    diagnostic_rows = [row for row in rows if row["record_kind"] == "diagnostic"]
    assert len(diagnostic_rows) == 1
    assert diagnostic_rows[0]["name"] == "provider-fallback"
    assert diagnostic_rows[0]["category"] == "provider"
    assert diagnostic_rows[0]["status"] == "warning"
    assert diagnostic_rows[0]["error_code"] == "ORT_PROVIDER_FALLBACK"

    path = tmp_path / "run.parquet"
    _atomic_write_parquet(path, rows)

    capsule = read_experiment_capsule(path)
    assert len(capsule.diagnostics) == 1
    assert capsule.diagnostics[0]["error_stage"] == "inference"
    assert capsule.diagnostic_metadata(0) == {
        "assigned_nodes": 110,
        "fallback_nodes": 3,
    }


def test_multiple_diagnostics_preserve_input_order() -> None:
    rows = build_experiment_capsule_rows(
        run_context={"run_id": "run-001"},
        samples=[],
        benchmark=_benchmark(),
        diagnostics=[
            CapsuleDiagnostic(name="first", category="runtime"),
            CapsuleDiagnostic(name="second", category="parity", status="error"),
        ],
    )

    diagnostic_rows = [row for row in rows if row["record_kind"] == "diagnostic"]
    assert [row["name"] for row in diagnostic_rows] == ["first", "second"]
    assert diagnostic_rows[1]["ordinal"] == diagnostic_rows[0]["ordinal"] + 1
