use asr_contracts::{validate_rtf_benchmark_record, validate_rtf_service_metrics, validate_rtf_service_result};
use serde_json::json;

#[test]
fn accepts_completed_service_result() {
    let value = json!({
        "schema_version": 1,
        "run_id": "run-1",
        "service_id": "hf-jobs",
        "status": "completed",
        "provider": "cuda",
        "environment": "linux",
        "job_id": "job-1",
        "result_uri": "hf://buckets/example/runs/run-1/metrics.json",
        "result_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    });
    assert!(validate_rtf_service_result(&value).is_ok());
}

#[test]
fn rejects_blocked_result_without_error_code() {
    let value = json!({
        "schema_version": 1,
        "run_id": "run-1",
        "service_id": "runpod-pod",
        "status": "blocked",
        "provider": "cuda",
        "environment": "linux"
    });
    assert!(validate_rtf_service_result(&value).is_err());
}

#[test]
fn accepts_metrics_with_nullable_telemetry() {
    let value = json!({
        "schema_version": 1,
        "run_id": "run-1",
        "status": "completed",
        "model_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
        "model_revision": "model-revision-1",
        "dataset_id": "japanese-asr/ja_asr.jsut_basic5000",
        "dataset_revision": "dataset-revision-1",
        "manifest_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "image_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "inspection_profile": "smoke",
        "fixture_repo_id": "gawohok7/rtf-benchmark-fixtures",
        "fixture_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "decoder": "tdt",
        "audio_duration_sec": 10.0,
        "processing_duration_sec": 2.0,
        "rtf": 0.2,
        "rtfx": 5.0,
        "rtf_scope": "service",
        "provider": "cuda",
        "environment": "linux",
        "service_id": "hf-jobs",
        "gpu": "NVIDIA L4",
        "dtype": "float16",
        "batch_size": 1,
        "repeat": 3,
        "cer": null,
        "peak_vram_bytes": null,
        "gpu_utilization_pct": null,
        "gpu_price_per_hour": null,
        "cost_per_audio_hour": null
    });
    assert!(validate_rtf_service_metrics(&value).is_ok());
}

#[test]
fn rejects_metrics_with_zero_audio_duration() {
    let value = json!({
        "schema_version": 1,
        "run_id": "run-1",
        "model_id": "model",
        "dataset_id": "dataset",
        "dataset_revision": "revision",
        "manifest_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "audio_duration_sec": 0,
        "processing_duration_sec": 1.0,
        "rtf": 1.0,
        "rtfx": 1.0,
        "rtf_scope": "model",
        "provider": "cpu",
        "environment": "linux",
        "gpu": null,
        "dtype": "float32",
        "batch_size": 1,
        "cer": null,
        "peak_vram_bytes": null,
        "gpu_utilization_pct": null,
        "gpu_price_per_hour": null,
        "cost_per_audio_hour": null
    });
    assert!(validate_rtf_service_metrics(&value).is_err());
}

#[test]
fn completed_benchmark_record_requires_execution_proof_and_metrics() {
    let mut value = json!({
        "schema_version": 1, "run_id": "run-1", "phase": "phase1", "service_id": "runpod-pod", "gpu": "a5000", "model_id": "model", "decoder": "tdt",
        "dataset_manifest_id": "manifest-1", "dataset_manifest_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "dataset_revision": "revision-1", "fixture_repo_id": "gawohok7/rtf-benchmark-fixtures", "fixture_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "image_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "batch_size": 8, "repeat": 3, "precision": "float16", "status": "completed", "provider_execution_proof": false, "audio_duration_sec": 10.0, "processing_duration_sec": 1.0, "rtf": 0.1, "rtfx": 10.0, "rtf_scope": "service",
        "cer": 0.1, "wer": 0.2, "peak_vram_mb": 1000, "gpu_utilization_percent": 90, "gpu_price_per_hour": 0.27, "cost_per_audio_hour": 0.027, "metrics_uri": "hf://metrics/run-1.json", "metrics_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    });
    assert!(validate_rtf_benchmark_record(&value).is_err());
    value["provider_execution_proof"] = serde_json::Value::Bool(true);
    assert!(validate_rtf_benchmark_record(&value).is_ok());
}
