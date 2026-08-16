use std::{fs, path::PathBuf, time::Instant};

use asr_audio::{decode_audio, CanonicalAudio};
use asr_metrics::{character_error_rate, normalize_text, word_error_rate};
use asr_runtime::{
    metadata::model_metadata::GeneratedCandidateContract, OrtCtcSession, ProviderKind,
    SessionConfig, SessionTuning,
};

use crate::{
    benchmark::{build_benchmark, ProviderTelemetry, SampleAggregate},
    decoding::ctc::Vocabulary,
    manifest::load_resolved_manifest,
    writer::{ensure_dir, write_json, write_jsonl},
    EvalError, Result,
};

#[derive(Debug, Clone)]
pub struct EvaluateOptions {
    pub provider: ProviderKind,
    pub candidate_contract: PathBuf,
    pub run_context: PathBuf,
    pub resolved_manifest: PathBuf,
    pub output: PathBuf,
}

pub fn evaluate(options: EvaluateOptions) -> Result<serde_json::Value> {
    let manifest = load_resolved_manifest(&options.resolved_manifest)?;
    let candidate = GeneratedCandidateContract::load(&options.candidate_contract)?;
    let ctc_contract = candidate.ctc_runtime_contract()?;
    let model_path = candidate.artifact_path("primary")?;
    let vocabulary_path = candidate.tokenizer_path()?;
    let vocabulary = Vocabulary::load(&vocabulary_path)?;

    let mut run_context: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&options.run_context)?)?;
    validate_execution_inputs(&run_context, &candidate, options.provider, &model_path)?;

    let tuning = SessionTuning::from_run_context(&run_context)?;
    let strict_provider = options.provider != ProviderKind::Cpu && !tuning.allow_cpu_fallback;
    let mut session = OrtCtcSession::create(
        SessionConfig::new(&model_path, options.provider, tuning),
        ctc_contract,
    )?;
    let session_creation_ms = session.session_creation_ms();

    run_context["runtime"]["provider_available"] = serde_json::Value::Bool(true);
    run_context["metadata"]["provider_readiness"] = serde_json::json!({
        "compiled": options.provider.compiled(),
        "registered": true,
        "session_created": true,
        "execution_proven": false,
        "assignment_proven": options.provider == ProviderKind::Cpu,
        "strict_provider": strict_provider,
        "cpu_fallback_allowed": session.cpu_fallback_allowed(),
        "evidence": if options.provider == ProviderKind::Cpu {
            "cpu_provider_selected"
        } else if strict_provider {
            "session_created_with_cpu_fallback_disabled; awaiting successful inference"
        } else {
            "session_created_with_cpu_fallback_allowed; requested EP execution is not inferred"
        }
    });

    ensure_dir(&options.output)?;
    let run_id = run_context["run_id"]
        .as_str()
        .ok_or_else(|| EvalError::InvalidInput("run-context run_id is missing".into()))?
        .to_owned();
    let mut results = Vec::with_capacity(manifest.samples.len());
    let mut aggregate = SampleAggregate::default();

    for sample in &manifest.samples {
        let started = Instant::now();
        let result = (|| -> Result<serde_json::Value> {
            let audio_path = sample.audio_path.as_deref().ok_or_else(|| {
                EvalError::InvalidInput(format!(
                    "resolved sample {} has no materialized audio_path",
                    sample.id
                ))
            })?;

            let decode_started = Instant::now();
            let decoded = decode_audio(audio_path)?;
            let decode_ms = decode_started.elapsed().as_secs_f64() * 1000.0;

            let resample_started = Instant::now();
            let canonical = CanonicalAudio::from_decoded(decoded)?;
            let resample_ms = resample_started.elapsed().as_secs_f64() * 1000.0;

            let inference = session.run_waveform(&canonical.waveform)?;

            let decoder_started = Instant::now();
            let text = vocabulary.decode(&inference.token_ids)?;
            let decoder_ms = decoder_started.elapsed().as_secs_f64() * 1000.0;

            let post_started = Instant::now();
            let normalized = normalize_text(&text);
            let post_ms = post_started.elapsed().as_secs_f64() * 1000.0;
            let total_ms = started.elapsed().as_secs_f64() * 1000.0;
            let cer = character_error_rate(&sample.transcription, &text);
            let wer = word_error_rate(&sample.transcription, &text);

            aggregate.add_success(
                canonical.duration_sec(),
                cer,
                wer,
                total_ms,
                decode_ms,
                resample_ms,
                inference.inference_ms,
                decoder_ms,
                post_ms,
            );

            Ok(serde_json::json!({
                "schema_version": 1,
                "run_id": run_id,
                "sample": {
                    "id": sample.id,
                    "dataset_id": sample.dataset_id,
                    "dataset_repo_id": sample.dataset_repo_id,
                    "dataset_revision": sample.dataset_revision,
                    "subset": sample.subset,
                    "split": sample.split,
                    "index": sample.row_index,
                    "audio_sha256": sample.audio_sha256,
                    "audio_duration_sec": canonical.duration_sec(),
                    "sample_rate_hz": canonical.sample_rate_hz,
                    "reference_text": sample.transcription
                },
                "execution": {
                    "runtime": "rust",
                    "backend": "onnxruntime",
                    "provider_id": options.provider.to_string(),
                    "decoder": "ctc",
                    "batch_size": 1
                },
                "output": {
                    "text": text,
                    "normalized_text": normalized,
                    "tokens": inference.token_ids,
                    "token_count": inference.token_ids.len()
                },
                "quality": {"cer": cer, "wer": wer},
                "timing": {
                    "load_ms": null,
                    "session_creation_ms": null,
                    "audio_decode_ms": decode_ms,
                    "resample_ms": resample_ms,
                    "frontend_ms": null,
                    "encoder_ms": null,
                    "decoder_ms": decoder_ms,
                    "postprocess_ms": post_ms,
                    "inference_ms": inference.inference_ms,
                    "total_ms": total_ms,
                    "rtf": total_ms / 1000.0 / canonical.duration_sec()
                },
                "memory": {
                    "peak_ram_mb": asr_metrics::current_process_memory_mb(),
                    "peak_device_memory_mb": null
                },
                "parity": unavailable_parity(),
                "provider": sample_provider(options.provider, strict_provider, true),
                "status": "success",
                "errors": []
            }))
        })();

        match result {
            Ok(value) => results.push(value),
            Err(error) => {
                aggregate.add_failure();
                results.push(serde_json::json!({
                    "schema_version": 1,
                    "run_id": run_id,
                    "sample": {
                        "id": sample.id,
                        "dataset_id": sample.dataset_id,
                        "dataset_repo_id": sample.dataset_repo_id,
                        "dataset_revision": sample.dataset_revision,
                        "subset": sample.subset,
                        "split": sample.split,
                        "index": sample.row_index,
                        "audio_sha256": sample.audio_sha256,
                        "audio_duration_sec": sample.duration_sec,
                        "sample_rate_hz": sample.sample_rate_hz.unwrap_or(16_000),
                        "reference_text": sample.transcription
                    },
                    "execution": {
                        "runtime": "rust",
                        "backend": "onnxruntime",
                        "provider_id": options.provider.to_string(),
                        "decoder": "ctc",
                        "batch_size": 1
                    },
                    "output": {"text":"","normalized_text":"","tokens":[],"token_count":0},
                    "quality": {"cer":null,"wer":null},
                    "timing": {
                        "load_ms":null,"session_creation_ms":null,"audio_decode_ms":null,
                        "resample_ms":null,"frontend_ms":null,"encoder_ms":null,
                        "decoder_ms":null,"postprocess_ms":null,"inference_ms":null,
                        "total_ms":started.elapsed().as_secs_f64()*1000.0,"rtf":null
                    },
                    "memory":{"peak_ram_mb":null,"peak_device_memory_mb":null},
                    "parity": unavailable_parity(),
                    "provider": sample_provider(options.provider, strict_provider, false),
                    "status":"failed",
                    "errors":[{"code":"SAMPLE_EVALUATION_FAILED","stage":"inference","message":error.to_string(),"fatal":true}]
                }));
            }
        }
    }

    let telemetry = finalized_provider_telemetry(options.provider, strict_provider, &aggregate);
    let readiness = &mut run_context["metadata"]["provider_readiness"];
    readiness["execution_proven"] = serde_json::Value::Bool(telemetry.used == Some(true));
    readiness["assignment_proven"] = serde_json::Value::Bool(
        options.provider == ProviderKind::Cpu || telemetry.assigned_nodes.is_some(),
    );
    readiness["evidence"] = serde_json::Value::String(
        if options.provider == ProviderKind::Cpu && aggregate.successful > 0 {
            "cpu inference succeeded"
        } else if strict_provider && aggregate.successful > 0 {
            "inference succeeded with CPU fallback disabled; node assignment remains unmeasured"
        } else if aggregate.successful > 0 {
            "inference succeeded with CPU fallback allowed; requested EP execution remains unproven"
        } else {
            "no successful inference"
        }
        .to_owned(),
    );

    write_json(&options.output.join("run-context.json"), &run_context)?;
    write_jsonl(&options.output.join("samples.jsonl"), &results)?;
    let benchmark = build_benchmark(
        &run_context,
        &manifest.manifest_path,
        manifest.expected_sample_count,
        session_creation_ms,
        &options.provider.to_string(),
        options.provider.ort_name(),
        telemetry,
        &aggregate,
    );
    write_json(&options.output.join("metrics.json"), &benchmark)?;
    Ok(benchmark)
}

fn validate_execution_inputs(
    context: &serde_json::Value,
    candidate: &GeneratedCandidateContract,
    provider: ProviderKind,
    model_path: &std::path::Path,
) -> Result<()> {
    if context.get("schema_version").and_then(serde_json::Value::as_u64) != Some(2) {
        return Err(EvalError::InvalidInput(
            "Rust evaluator requires run-context schema_version 2".into(),
        ));
    }
    let provider_id = provider.to_string();
    if context.get("provider_id").and_then(serde_json::Value::as_str) != Some(provider_id.as_str()) {
        return Err(EvalError::InvalidInput(
            "run-context provider_id does not match requested provider".into(),
        ));
    }
    let provenance = &context["metadata"]["candidate"];
    for (name, actual, expected) in [
        ("candidate_id", provenance["candidate_id"].as_str(), Some(candidate.candidate_id.as_str())),
        ("variant", provenance["variant"].as_str(), Some(candidate.variant.as_str())),
        ("profile", provenance["profile"].as_str(), Some(candidate.profile.as_str())),
        ("bundle_sha256", provenance["bundle_sha256"].as_str(), Some(candidate.bundle_sha256.as_str())),
    ] {
        if actual != expected {
            return Err(EvalError::InvalidInput(format!(
                "run-context candidate {name} does not match generated candidate contract"
            )));
        }
    }
    let artifact_path = context["artifact"]["path"]
        .as_str()
        .ok_or_else(|| EvalError::InvalidInput("run-context artifact.path is missing".into()))?;
    if !artifact_path.ends_with(
        model_path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or_default(),
    ) {
        return Err(EvalError::InvalidInput(
            "run-context artifact path does not match selected primary artifact".into(),
        ));
    }
    Ok(())
}

fn finalized_provider_telemetry(
    provider: ProviderKind,
    strict_provider: bool,
    aggregate: &SampleAggregate,
) -> ProviderTelemetry {
    let executed = aggregate.successful > 0;
    if provider == ProviderKind::Cpu {
        ProviderTelemetry {
            registered: true,
            used: Some(executed),
            fallback_detected: Some(false),
            fallback_only: Some(false),
            assigned_nodes: None,
            fallback_nodes: Some(0),
        }
    } else if strict_provider {
        ProviderTelemetry {
            registered: true,
            used: Some(executed),
            fallback_detected: Some(false),
            fallback_only: Some(false),
            assigned_nodes: None,
            fallback_nodes: Some(0),
        }
    } else {
        ProviderTelemetry {
            registered: true,
            used: None,
            fallback_detected: None,
            fallback_only: None,
            assigned_nodes: None,
            fallback_nodes: None,
        }
    }
}

fn sample_provider(provider: ProviderKind, strict_provider: bool, success: bool) -> serde_json::Value {
    let proven = provider == ProviderKind::Cpu || strict_provider;
    serde_json::json!({
        "requested": provider.to_string(),
        "registered": true,
        "used": if proven { Some(success) } else { None },
        "fallback_detected": if proven { Some(false) } else { None },
        "fallback_only": if proven { Some(false) } else { None },
        "assigned_nodes": null,
        "fallback_nodes": if proven { Some(0) } else { None }
    })
}

fn unavailable_parity() -> serde_json::Value {
    serde_json::json!({
        "reference_run_id":null,"text_match":null,"token_match":null,
        "numeric":{
            "frontend":{"compared":false,"passed":null,"max_abs_error":null,"mean_abs_error":null,"relative_l2":null},
            "encoder":{"compared":false,"passed":null,"max_abs_error":null,"mean_abs_error":null,"relative_l2":null},
            "logits":{"compared":false,"passed":null,"max_abs_error":null,"mean_abs_error":null,"relative_l2":null}
        }
    })
}
