use std::{fs::File, path::Path};

use anyhow::{Context, Result, bail};
use arrow_array::{Array, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

use crate::{
    model::{ONNX_CAPSULE_SCHEMA_VERSION, OnnxCapsule, OnnxCapsuleManifest, OnnxCapsuleMetric, OnnxCapsuleSample},
    schema::onnx_capsule_v1_schema,
};

pub fn read_onnx_capsule(path: impl AsRef<Path>) -> Result<OnnxCapsule> {
    let path = path.as_ref();
    let file = File::open(path).with_context(|| format!("failed to open ONNX capsule {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)?;
    let observed = builder.schema().clone();
    let expected = onnx_capsule_v1_schema();
    if observed.as_ref() != expected.as_ref() {
        bail!("ONNX capsule Parquet schema does not exactly match jpapt.onnx-capsule.v1");
    }
    let reader = builder.with_batch_size(512).build()?;
    let mut manifest: Option<OnnxCapsuleManifest> = None;
    let mut samples = Vec::new();
    let mut metrics = Vec::new();
    let mut manifest_rows = 0usize;

    for batch in reader {
        let batch = batch?;
        for row in 0..batch.num_rows() {
            let schema_version = required_string(&batch, "schema_version", row)?;
            if schema_version != ONNX_CAPSULE_SCHEMA_VERSION { bail!("unsupported ONNX capsule schema_version {schema_version}"); }
            let row_manifest = manifest_from_row(&batch, row)?;
            if let Some(expected_manifest) = &manifest {
                if expected_manifest != &row_manifest { bail!("ONNX capsule common identity changes between rows"); }
            } else {
                manifest = Some(row_manifest);
            }
            match required_string(&batch, "record_kind", row)? {
                "manifest" => {
                    manifest_rows += 1;
                    if required_i64(&batch, "ordinal", row)? != 0 { bail!("manifest row ordinal must be zero"); }
                }
                "sample" => samples.push(sample_from_row(&batch, row)?),
                "metric" => metrics.push(metric_from_row(&batch, row)?),
                other => bail!("unsupported ONNX capsule record_kind {other}"),
            }
        }
    }
    if manifest_rows != 1 { bail!("ONNX capsule must contain exactly one manifest row"); }
    let capsule = OnnxCapsule {
        manifest: manifest.ok_or_else(|| anyhow::anyhow!("ONNX capsule contains no rows"))?,
        samples,
        metrics,
    };
    capsule.validate()?;
    Ok(capsule)
}

fn manifest_from_row(batch: &RecordBatch, row: usize) -> Result<OnnxCapsuleManifest> {
    Ok(OnnxCapsuleManifest {
        run_id: required_string(batch, "run_id", row)?.to_owned(),
        model_id: required_string(batch, "model_id", row)?.to_owned(),
        source_framework: required_string(batch, "source_framework", row)?.to_owned(),
        source_revision: required_string(batch, "source_revision", row)?.to_owned(),
        candidate_id: required_string(batch, "candidate_id", row)?.to_owned(),
        provider_id: required_string(batch, "provider_id", row)?.to_owned(),
        decoder: required_string(batch, "decoder", row)?.to_owned(),
        environment_id: required_string(batch, "environment_id", row)?.to_owned(),
        evaluation_input_id: required_string(batch, "evaluation_input_id", row)?.to_owned(),
        git_commit: required_string(batch, "git_commit", row)?.to_owned(),
        runtime_backend: required_string(batch, "runtime_backend", row)?.to_owned(),
        provider_registered: required_bool(batch, "provider_registered", row)?,
        provider_execution_proven: optional_bool(batch, "provider_execution_proven", row)?,
        provider_assignment_proven: optional_bool(batch, "provider_assignment_proven", row)?,
        fallback_detected: optional_bool(batch, "fallback_detected", row)?,
    })
}

fn sample_from_row(batch: &RecordBatch, row: usize) -> Result<OnnxCapsuleSample> {
    let sample_rate_hz = u32::try_from(required_i64(batch, "sample_rate_hz", row)?)
        .map_err(|_| anyhow::anyhow!("sample_rate_hz is outside u32 range at row {row}"))?;
    Ok(OnnxCapsuleSample {
        sample_id: required_string(batch, "sample_id", row)?.to_owned(),
        dataset_id: required_string(batch, "dataset_id", row)?.to_owned(),
        dataset_repo_id: required_string(batch, "dataset_repo_id", row)?.to_owned(),
        dataset_revision: required_string(batch, "dataset_revision", row)?.to_owned(),
        audio_sha256: required_string(batch, "audio_sha256", row)?.to_owned(),
        audio_duration_sec: required_f64(batch, "audio_duration_sec", row)?,
        sample_rate_hz,
        reference_text: required_string(batch, "reference_text", row)?.to_owned(),
        hypothesis_text: required_string(batch, "hypothesis_text", row)?.to_owned(),
        normalized_text: required_string(batch, "normalized_text", row)?.to_owned(),
        cer: optional_f64(batch, "cer", row)?,
        wer: optional_f64(batch, "wer", row)?,
        audio_decode_ms: optional_f64(batch, "audio_decode_ms", row)?,
        resample_ms: optional_f64(batch, "resample_ms", row)?,
        inference_ms: optional_f64(batch, "inference_ms", row)?,
        decoder_ms: optional_f64(batch, "decoder_ms", row)?,
        postprocess_ms: optional_f64(batch, "postprocess_ms", row)?,
        total_ms: required_f64(batch, "total_ms", row)?,
        rtf: optional_f64(batch, "rtf", row)?,
        peak_ram_mb: optional_f64(batch, "peak_ram_mb", row)?,
        peak_device_memory_mb: optional_f64(batch, "peak_device_memory_mb", row)?,
        status: required_string(batch, "status", row)?.to_owned(),
        error_code: optional_string(batch, "error_code", row)?.map(str::to_owned),
        error_stage: optional_string(batch, "error_stage", row)?.map(str::to_owned),
        error_message: optional_string(batch, "error_message", row)?.map(str::to_owned),
    })
}

fn metric_from_row(batch: &RecordBatch, row: usize) -> Result<OnnxCapsuleMetric> {
    Ok(OnnxCapsuleMetric {
        name: required_string(batch, "metric_name", row)?.to_owned(),
        value: required_f64(batch, "metric_value", row)?,
        unit: optional_string(batch, "metric_unit", row)?.map(str::to_owned),
    })
}

fn column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a dyn Array> {
    let index = batch.schema().index_of(name)?;
    Ok(batch.column(index).as_ref())
}
fn required_string<'a>(batch: &'a RecordBatch, name: &str, row: usize) -> Result<&'a str> {
    optional_string(batch, name, row)?.ok_or_else(|| anyhow::anyhow!("column {name} is null at row {row}"))
}
fn optional_string<'a>(batch: &'a RecordBatch, name: &str, row: usize) -> Result<Option<&'a str>> {
    let array = column(batch, name)?.as_any().downcast_ref::<StringArray>()
        .ok_or_else(|| anyhow::anyhow!("column {name} is not Utf8"))?;
    Ok((!array.is_null(row)).then(|| array.value(row)))
}
fn required_f64(batch: &RecordBatch, name: &str, row: usize) -> Result<f64> {
    optional_f64(batch, name, row)?.ok_or_else(|| anyhow::anyhow!("column {name} is null at row {row}"))
}
fn optional_f64(batch: &RecordBatch, name: &str, row: usize) -> Result<Option<f64>> {
    let array = column(batch, name)?.as_any().downcast_ref::<Float64Array>()
        .ok_or_else(|| anyhow::anyhow!("column {name} is not Float64"))?;
    if array.is_null(row) { return Ok(None); }
    let value = array.value(row);
    if !value.is_finite() { bail!("column {name} contains NaN/Infinity at row {row}"); }
    Ok(Some(value))
}
fn required_i64(batch: &RecordBatch, name: &str, row: usize) -> Result<i64> {
    let array = column(batch, name)?.as_any().downcast_ref::<Int64Array>()
        .ok_or_else(|| anyhow::anyhow!("column {name} is not Int64"))?;
    if array.is_null(row) { bail!("column {name} is null at row {row}"); }
    Ok(array.value(row))
}
fn required_bool(batch: &RecordBatch, name: &str, row: usize) -> Result<bool> {
    optional_bool(batch, name, row)?.ok_or_else(|| anyhow::anyhow!("column {name} is null at row {row}"))
}
fn optional_bool(batch: &RecordBatch, name: &str, row: usize) -> Result<Option<bool>> {
    let array = column(batch, name)?.as_any().downcast_ref::<BooleanArray>()
        .ok_or_else(|| anyhow::anyhow!("column {name} is not Boolean"))?;
    Ok((!array.is_null(row)).then(|| array.value(row)))
}
