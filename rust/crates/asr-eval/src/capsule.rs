use std::path::Path;

use asr_onnx_capsule::{
    OnnxCapsule, OnnxCapsuleManifest, OnnxCapsuleMetric, OnnxCapsuleSample, write_onnx_capsule,
};
use serde_json::Value;

use crate::{EvalError, Result, dataset::ResolvedManifest, writer::write_json};

pub fn write_onnx_evaluation_capsule(
    output: &Path,
    run_context: &Value,
    input: &ResolvedManifest,
    rows: &[Value],
    benchmark: &Value,
) -> Result<()> {
    let manifest = OnnxCapsuleManifest {
        run_id: required_str(run_context, &["run_id"], "run_context.run_id")?.to_owned(),
        model_id: required_str(run_context, &["model_id"], "run_context.model_id")?.to_owned(),
        source_framework: required_str(
            run_context,
            &["revisions", "reference", "canonical_framework"],
            "run_context.revisions.reference.canonical_framework",
        )?.to_owned(),
        source_revision: required_str(
            run_context,
            &["revisions", "reference", "upstream", "revision"],
            "run_context.revisions.reference.upstream.revision",
        )?.to_owned(),
        candidate_id: required_str(
            run_context,
            &["metadata", "candidate", "candidate_id"],
            "run_context.metadata.candidate.candidate_id",
        )?.to_owned(),
        provider_id: required_str(run_context, &["provider_id"], "run_context.provider_id")?.to_owned(),
        decoder: required_str(
            run_context,
            &["metadata", "candidate", "decoder"],
            "run_context.metadata.candidate.decoder",
        )?.to_owned(),
        environment_id: required_str(run_context, &["environment_id"], "run_context.environment_id")?.to_owned(),
        evaluation_input_id: input.input_id.clone(),
        git_commit: required_str(run_context, &["git", "commit"], "run_context.git.commit")?.to_owned(),
        runtime_backend: "onnxruntime".to_owned(),
        provider_registered: benchmark.pointer("/provider/registered").and_then(Value::as_bool)
            .ok_or_else(|| invalid("benchmark provider.registered must be boolean"))?,
        provider_execution_proven: optional_bool(benchmark, "/provider/execution_proven")?,
        provider_assignment_proven: optional_assignment(benchmark)?,
        fallback_detected: optional_bool(benchmark, "/provider/fallback_detected")?,
    };

    let samples = rows.iter().map(sample_from_json).collect::<Result<Vec<_>>>()?;
    if samples.len() != input.samples.len() {
        return Err(invalid("ONNX capsule sample count does not match normalized evaluation input"));
    }

    let mut metrics = Vec::new();
    push_metric(&mut metrics, benchmark, "/quality/cer", "cer", Some("ratio"))?;
    push_metric(&mut metrics, benchmark, "/quality/wer", "wer", Some("ratio"))?;
    push_metric(&mut metrics, benchmark, "/performance/rtf", "rtf", Some("ratio"))?;
    push_metric(&mut metrics, benchmark, "/performance/session_creation_ms", "session_creation_ms", Some("ms"))?;
    push_metric(&mut metrics, benchmark, "/performance/total_processing_ms", "total_processing_ms", Some("ms"))?;

    let capsule = OnnxCapsule { manifest, samples, metrics };
    let receipt = write_onnx_capsule(output.join("onnx-capsule.parquet"), &capsule)
        .map_err(|error| invalid(format!("failed to write ONNX capsule: {error}")))?;
    write_json(&output.join("onnx-capsule-receipt.json"), &serde_json::to_value(receipt)?)?;
    Ok(())
}

fn sample_from_json(row: &Value) -> Result<OnnxCapsuleSample> {
    let status = required_str(row, &["status"], "sample.status")?;
    let error = row.get("errors").and_then(Value::as_array).and_then(|errors| errors.first());
    Ok(OnnxCapsuleSample {
        sample_id: required_str(row, &["sample", "id"], "sample.id")?.to_owned(),
        dataset_id: required_str(row, &["sample", "dataset_id"], "sample.dataset_id")?.to_owned(),
        dataset_repo_id: required_str(row, &["sample", "dataset_repo_id"], "sample.dataset_repo_id")?.to_owned(),
        dataset_revision: required_str(row, &["sample", "dataset_revision"], "sample.dataset_revision")?.to_owned(),
        audio_sha256: required_str(row, &["sample", "audio_sha256"], "sample.audio_sha256")?.to_owned(),
        audio_duration_sec: required_f64(row, "/sample/audio_duration_sec")?,
        sample_rate_hz: u32::try_from(required_u64(row, "/sample/sample_rate_hz")?)
            .map_err(|_| invalid("sample.sample_rate_hz is outside u32 range"))?,
        reference_text: required_str(row, &["sample", "reference_text"], "sample.reference_text")?.to_owned(),
        hypothesis_text: required_str(row, &["output", "text"], "output.text")?.to_owned(),
        normalized_text: required_str(row, &["output", "normalized_text"], "output.normalized_text")?.to_owned(),
        cer: optional_f64(row, "/quality/cer")?,
        wer: optional_f64(row, "/quality/wer")?,
        audio_decode_ms: optional_f64(row, "/timing/audio_decode_ms")?,
        resample_ms: optional_f64(row, "/timing/resample_ms")?,
        inference_ms: optional_f64(row, "/timing/inference_ms")?,
        decoder_ms: optional_f64(row, "/timing/decoder_ms")?,
        postprocess_ms: optional_f64(row, "/timing/postprocess_ms")?,
        total_ms: required_f64(row, "/timing/total_ms")?,
        rtf: optional_f64(row, "/timing/rtf")?,
        peak_ram_mb: optional_f64(row, "/memory/peak_ram_mb")?,
        peak_device_memory_mb: optional_f64(row, "/memory/peak_device_memory_mb")?,
        status: status.to_owned(),
        error_code: error.and_then(|value| value.get("code")).and_then(Value::as_str).map(str::to_owned),
        error_stage: error.and_then(|value| value.get("stage")).and_then(Value::as_str).map(str::to_owned),
        error_message: error.and_then(|value| value.get("message")).and_then(Value::as_str).map(str::to_owned),
    })
}

fn push_metric(metrics: &mut Vec<OnnxCapsuleMetric>, source: &Value, pointer: &str, name: &str, unit: Option<&str>) -> Result<()> {
    if let Some(value) = optional_f64(source, pointer)? {
        metrics.push(OnnxCapsuleMetric { name: name.to_owned(), value, unit: unit.map(str::to_owned) });
    }
    Ok(())
}

fn optional_assignment(benchmark: &Value) -> Result<Option<bool>> {
    match benchmark.pointer("/provider/assigned_nodes") {
        Some(Value::Number(number)) => Ok(Some(number.as_u64().is_some_and(|value| value > 0))),
        Some(Value::Null) | None => Ok(None),
        _ => Err(invalid("benchmark provider.assigned_nodes must be integer or null")),
    }
}

fn required_str<'a>(value: &'a Value, path: &[&str], label: &str) -> Result<&'a str> {
    let mut cursor = value;
    for key in path { cursor = cursor.get(*key).ok_or_else(|| invalid(format!("missing {label}")))?; }
    cursor.as_str().ok_or_else(|| invalid(format!("{label} must be a string")))
}
fn required_u64(value: &Value, pointer: &str) -> Result<u64> {
    value.pointer(pointer).and_then(Value::as_u64).ok_or_else(|| invalid(format!("{pointer} must be an unsigned integer")))
}
fn required_f64(value: &Value, pointer: &str) -> Result<f64> {
    optional_f64(value, pointer)?.ok_or_else(|| invalid(format!("{pointer} must be numeric")))
}
fn optional_f64(value: &Value, pointer: &str) -> Result<Option<f64>> {
    match value.pointer(pointer) {
        None | Some(Value::Null) => Ok(None),
        Some(number) => {
            let value = number.as_f64().ok_or_else(|| invalid(format!("{pointer} must be numeric or null")))?;
            if !value.is_finite() { return Err(invalid(format!("{pointer} must not be NaN/Infinity"))); }
            Ok(Some(value))
        }
    }
}
fn optional_bool(value: &Value, pointer: &str) -> Result<Option<bool>> {
    match value.pointer(pointer) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Bool(value)) => Ok(Some(*value)),
        _ => Err(invalid(format!("{pointer} must be boolean or null"))),
    }
}
fn invalid(message: impl Into<String>) -> EvalError { EvalError::InvalidInput(message.into()) }
