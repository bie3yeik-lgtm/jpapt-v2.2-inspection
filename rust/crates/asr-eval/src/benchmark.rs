use asr_metrics::{distribution, rtf_metrics};

#[derive(Debug, Clone)]
pub struct SampleAggregate {
    pub successful: usize,
    pub failed: usize,
    pub total_audio: f64,
    pub cer_sum: f64,
    pub wer_sum: f64,
    pub timing_ms: Vec<f64>,
    pub audio_decode_ms: f64,
    pub resample_ms: f64,
    pub decoder_ms: f64,
    pub postprocess_ms: f64,
    pub inference_ms: f64,
}

impl Default for SampleAggregate {
    fn default() -> Self {
        Self {
            successful: 0,
            failed: 0,
            total_audio: 0.0,
            cer_sum: 0.0,
            wer_sum: 0.0,
            timing_ms: Vec::new(),
            audio_decode_ms: 0.0,
            resample_ms: 0.0,
            decoder_ms: 0.0,
            postprocess_ms: 0.0,
            inference_ms: 0.0,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct ProviderTelemetry {
    pub registered: bool,
    pub used: Option<bool>,
    pub fallback_detected: Option<bool>,
    pub fallback_only: Option<bool>,
    pub assigned_nodes: Option<u64>,
    pub fallback_nodes: Option<u64>,
}

#[derive(Debug, Clone, Copy)]
pub struct BenchmarkInput<'a> {
    pub run_context: &'a serde_json::Value,
    pub manifest: &'a str,
    pub expected: usize,
    pub session_creation_ms: f64,
    pub provider: &'a str,
    pub provider_ort: &'a str,
    pub provider_telemetry: ProviderTelemetry,
    pub aggregate: &'a SampleAggregate,
}

impl SampleAggregate {
    #[allow(clippy::too_many_arguments)]
    pub fn add_success(
        &mut self,
        duration: f64,
        cer: f64,
        wer: f64,
        total_ms: f64,
        audio_decode_ms: f64,
        resample_ms: f64,
        inference_ms: f64,
        decoder_ms: f64,
        postprocess_ms: f64,
    ) {
        self.successful += 1;
        self.total_audio += duration;
        self.cer_sum += cer;
        self.wer_sum += wer;
        self.timing_ms.push(total_ms);
        self.audio_decode_ms += audio_decode_ms;
        self.resample_ms += resample_ms;
        self.inference_ms += inference_ms;
        self.decoder_ms += decoder_ms;
        self.postprocess_ms += postprocess_ms;
    }

    pub fn add_failure(&mut self) {
        self.failed += 1;
    }
}

pub fn build_benchmark(input: BenchmarkInput<'_>) -> serde_json::Value {
    let BenchmarkInput {
        run_context,
        manifest,
        expected,
        session_creation_ms,
        provider,
        provider_ort,
        provider_telemetry,
        aggregate: agg,
    } = input;
    let dist = distribution(&agg.timing_ms);
    let n = agg.successful.max(1) as f64;
    let total_ms = agg.timing_ms.iter().sum::<f64>();
    let passed = agg.failed == 0 && agg.successful == expected;
    let failed_checks: Vec<String> = if passed {
        Vec::new()
    } else {
        vec!["sample_execution".to_string()]
    };

    let candidate = &run_context["metadata"]["candidate"];
    let candidate_id = candidate["candidate_id"].clone();
    let model_id = run_context["model_id"].clone();
    let bundle_sha256 = candidate["bundle_sha256"].clone();
    let artifact_size_bytes = run_context["artifact"]["size_bytes"].clone();
    let decoder = candidate["decoder"].clone();

    let rtf = if agg.total_audio > 0.0 {
        rtf_metrics(agg.total_audio, total_ms / 1000.0).ok()
    } else {
        None
    };

    serde_json::json!({
        "schema_version": 1,
        "run_id": run_context["run_id"],
        "candidate": {
            "candidate_id": candidate_id,
            "model_id": model_id,
            "artifact_sha256": bundle_sha256,
            "artifact_size_bytes": artifact_size_bytes,
            "decoder": decoder
        },
        "evaluation": {
            "suite": run_context["evaluation_id"],
            "manifest": manifest,
            "expected_sample_count": expected,
            "reference_revision_sha256": run_context["revisions"]["reference"]["document_sha256"],
            "evaluation_schema_sha256": run_context["revisions"]["evaluation_schema"]["document_sha256"],
            "datasets_lock_sha256": run_context["revisions"]["datasets"]["document_sha256"],
            "revision_bundle_sha256": run_context["revisions"]["bundle_sha256"]
        },
        "runtime": {
            "implementation": "rust",
            "backend": "onnxruntime",
            "backend_version": asr_runtime::ort_build_info(),
            "environment_id": run_context["environment_id"],
            "provider_id": provider,
            "provider_ort_name": provider_ort,
            "os": std::env::consts::OS,
            "architecture": std::env::consts::ARCH
        },
        "samples": {
            "expected": expected,
            "attempted": agg.successful + agg.failed,
            "successful": agg.successful,
            "failed": agg.failed,
            "skipped": 0,
            "total_audio_duration_sec": agg.total_audio
        },
        "quality": {
            "cer": if agg.successful > 0 { Some(agg.cer_sum / n) } else { None },
            "wer": if agg.successful > 0 { Some(agg.wer_sum / n) } else { None }
        },
        "performance": {
            "load_ms": null,
            "session_creation_ms": session_creation_ms,
            "total_processing_ms": total_ms,
            "rtf": rtf.map(|value| value.rtf),
            "rtfx": rtf.map(|value| value.rtfx),
            "rtf_scope": "model",
            "audio_hours_per_gpu_hour": rtf.map(|value| value.rtfx),
            "gpu_price_per_hour": null,
            "cost_per_audio_hour": null,
            "per_sample": {
                "mean_ms": dist.mean_ms,
                "median_ms": dist.median_ms,
                "p50_ms": dist.p50_ms,
                "p95_ms": dist.p95_ms,
                "p99_ms": dist.p99_ms,
                "min_ms": dist.min_ms,
                "max_ms": dist.max_ms
            },
            "components": {
                "audio_decode_ms": if agg.successful > 0 { Some(agg.audio_decode_ms / n) } else { None },
                "resample_ms": if agg.successful > 0 { Some(agg.resample_ms / n) } else { None },
                "frontend_ms": null,
                "encoder_ms": null,
                "decoder_ms": if agg.successful > 0 { Some(agg.decoder_ms / n) } else { None },
                "postprocess_ms": if agg.successful > 0 { Some(agg.postprocess_ms / n) } else { None },
                "inference_ms": if agg.successful > 0 { Some(agg.inference_ms / n) } else { None }
            }
        },
        "memory": {
            "peak_ram_mb": asr_metrics::current_process_memory_mb(),
            "peak_device_memory_mb": null
        },
        "parity": {
            "reference_run_id": null,
            "text_matches": 0,
            "text_mismatches": 0,
            "token_matches": 0,
            "token_mismatches": 0,
            "text_match_rate": null,
            "token_match_rate": null,
            "numeric": {
                "frontend": {"compared_samples":0,"failed_samples":0,"max_abs_error":null,"max_mean_abs_error":null,"max_relative_l2":null},
                "encoder": {"compared_samples":0,"failed_samples":0,"max_abs_error":null,"max_mean_abs_error":null,"max_relative_l2":null},
                "logits": {"compared_samples":0,"failed_samples":0,"max_abs_error":null,"max_mean_abs_error":null,"max_relative_l2":null}
            }
        },
        "provider": {
            "requested": provider,
            "registered": provider_telemetry.registered,
            "execution_proven": provider_telemetry.used,
            "fallback_detected": provider_telemetry.fallback_detected,
            "fallback_only": provider_telemetry.fallback_only,
            "assigned_nodes": provider_telemetry.assigned_nodes,
            "fallback_nodes": provider_telemetry.fallback_nodes
        },
        "acceptance": {
            "passed": passed,
            "quality_passed": null,
            "parity_passed": null,
            "provider_passed": null,
            "performance_passed": null,
            "failed_checks": failed_checks,
            "warnings": ["threshold-based acceptance remains controlled by evaluation-schema.json"]
        },
        "errors": {
            "total": agg.failed,
            "fatal": agg.failed,
            "by_code": {}
        }
    })
}
