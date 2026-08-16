from __future__ import annotations

from datasets import Dataset
import pytest

from parakeet_onnx.evaluation import (
    ExperimentCapsuleError,
    read_experiment_capsule,
    validate_experiment_capsule,
)
from parakeet_onnx.evaluation.parquet import (
    EXPERIMENT_CAPSULE_SCHEMA_VERSION,
    _atomic_write_parquet,
    build_experiment_capsule_rows,
)


def _sample(run_id: str = "run-001") -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "sample": {
            "id": "sample-001",
            "dataset_id": "jsut-basic5000",
            "dataset_repo_id": "japanese-asr/ja_asr.jsut_basic5000",
            "dataset_revision": "a" * 40,
            "subset": None,
            "split": "test",
            "index": 3,
            "audio_sha256": "b" * 64,
            "audio_duration_sec": 1.25,
            "sample_rate_hz": 16000,
            "reference_text": "参照テキスト",
        },
        "execution": {
            "runtime": "python",
            "backend": "onnxruntime",
            "provider_id": "cpu",
            "decoder": "ctc",
            "batch_size": 1,
        },
        "output": {
            "text": "認識テキスト",
            "normalized_text": "認識テキスト",
            "tokens": [1, 2, 3],
            "token_count": 3,
        },
        "quality": {"cer": 0.1, "wer": 0.2},
        "timing": {
            "load_ms": 2.0,
            "session_creation_ms": 3.0,
            "audio_decode_ms": 4.0,
            "resample_ms": 5.0,
            "frontend_ms": 6.0,
            "encoder_ms": 7.0,
            "decoder_ms": 8.0,
            "postprocess_ms": 9.0,
            "inference_ms": 15.0,
            "total_ms": 20.0,
            "rtf": 0.016,
        },
        "memory": {
            "peak_ram_mb": 128.0,
            "peak_device_memory_mb": None,
        },
        "parity": {
            "reference_run_id": None,
            "text_match": None,
            "token_match": None,
            "numeric": {},
        },
        "provider": {
            "requested": "cpu",
            "registered": True,
            "used": True,
            "fallback_detected": False,
            "fallback_only": False,
            "assigned_nodes": 12,
            "fallback_nodes": 0,
        },
        "status": "success",
        "errors": [],
    }


def _benchmark(run_id: str = "run-001") -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "samples": {
            "expected": 1,
            "attempted": 1,
            "successful": 1,
            "failed": 0,
            "skipped": 0,
            "total_audio_duration_sec": 1.25,
        },
        "quality": {"cer": 0.1, "wer": 0.2},
        "performance": {
            "total_processing_ms": 20.0,
            "rtf": 0.016,
        },
        "memory": {"peak_ram_mb": 128.0},
        "parity": {
            "text_matches": 0,
            "text_mismatches": 0,
        },
        "provider": {
            "assigned_nodes": 12,
            "fallback_nodes": 0,
            "execution_proven": True,
        },
        "acceptance": {"passed": True},
        "errors": {"total": 0, "fatal": 0, "by_code": {}},
    }


def _rows() -> list[dict[str, object]]:
    return build_experiment_capsule_rows(
        run_context={"run_id": "run-001", "provider_id": "cpu"},
        samples=[_sample()],
        benchmark=_benchmark(),
    )


def test_build_experiment_capsule_rows_is_flat_and_deterministic() -> None:
    rows = _rows()

    assert rows[0]["record_kind"] == "manifest"
    assert rows[1]["record_kind"] == "sample"
    assert rows[1]["sample_id"] == "sample-001"
    assert rows[1]["hypothesis_text"] == "認識テキスト"
    assert rows[1]["schema_version"] == EXPERIMENT_CAPSULE_SCHEMA_VERSION

    metric_names = {
        row["metric_name"]
        for row in rows
        if row["record_kind"] == "metric"
    }
    assert "quality.cer" in metric_names
    assert "samples.total_audio_duration_sec" in metric_names
    assert "provider.execution_proven" not in metric_names
    assert [row["ordinal"] for row in rows] == list(range(len(rows)))


def test_build_experiment_capsule_rows_rejects_cross_run_sample() -> None:
    with pytest.raises(ValueError, match="sample result run_id"):
        build_experiment_capsule_rows(
            run_context={"run_id": "run-001"},
            samples=[_sample("run-other")],
            benchmark=_benchmark(),
        )


def test_atomic_write_parquet_round_trips_with_datasets(tmp_path) -> None:
    rows = _rows()
    path = tmp_path / "run.parquet"

    _atomic_write_parquet(path, rows)

    restored = Dataset.from_parquet(str(path))
    assert path.stat().st_size > 0
    assert restored.num_rows == len(rows)
    assert restored[0]["record_kind"] == "manifest"
    assert restored[1]["sample_id"] == "sample-001"


def test_reader_validates_and_exposes_samples_and_metrics(tmp_path) -> None:
    path = tmp_path / "run.parquet"
    _atomic_write_parquet(path, _rows())

    capsule = read_experiment_capsule(path)

    assert capsule.run_id == "run-001"
    assert len(capsule.samples) == 1
    assert capsule.samples[0]["sample_id"] == "sample-001"
    assert capsule.metric("quality.cer") == pytest.approx(0.1)
    assert validate_experiment_capsule(path, expected_run_id="run-001") == 1


def test_reader_rejects_expected_run_id_mismatch(tmp_path) -> None:
    path = tmp_path / "run.parquet"
    _atomic_write_parquet(path, _rows())

    with pytest.raises(ExperimentCapsuleError, match="expected run_id"):
        validate_experiment_capsule(path, expected_run_id="run-other")


def test_reader_rejects_benchmark_sample_count_mismatch(tmp_path) -> None:
    benchmark = _benchmark()
    assert isinstance(benchmark["samples"], dict)
    benchmark["samples"]["attempted"] = 2
    rows = build_experiment_capsule_rows(
        run_context={"run_id": "run-001", "provider_id": "cpu"},
        samples=[_sample()],
        benchmark=benchmark,
    )
    path = tmp_path / "run.parquet"
    _atomic_write_parquet(path, rows)

    with pytest.raises(ExperimentCapsuleError, match="samples.attempted"):
        read_experiment_capsule(path)
