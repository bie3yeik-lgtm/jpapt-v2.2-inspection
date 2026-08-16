use std::{fs::File, path::Path, sync::Arc};

use anyhow::{Context, Result};
use arrow_array::{
    ArrayRef, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray,
};
use arrow_schema::Schema;
use parquet::{
    arrow::ArrowWriter,
    basic::Compression,
    file::properties::WriterProperties,
};

use crate::{
    hash::sha256_file,
    model::{CAPSULE_SCHEMA_VERSION, CapsuleManifest, CapsuleMetric, CapsuleReceipt, CapsuleSample, ExperimentCapsule},
    schema::experiment_capsule_v1_schema,
};

const ROW_GROUP_ROWS: usize = 512;
const FLUSH_MEMORY_BYTES: usize = 16 * 1024 * 1024;

pub fn write_capsule(path: impl AsRef<Path>, capsule: &ExperimentCapsule) -> Result<CapsuleReceipt> {
    capsule.validate()?;
    let path = path.as_ref();
    let file = File::create(path)
        .with_context(|| format!("failed to create capsule {}", path.display()))?;
    let schema = experiment_capsule_v1_schema();
    let props = WriterProperties::builder()
        .set_compression(Compression::ZSTD(Default::default()))
        .set_max_row_group_size(ROW_GROUP_ROWS)
        .build();
    let mut writer = ArrowWriter::try_new(file, schema.clone(), Some(props))?;

    let manifest_row = Row::manifest();
    writer.write(&batch_from_rows(schema.clone(), &capsule.manifest, &[manifest_row])?)?;

    for (chunk_index, chunk) in capsule.samples.chunks(ROW_GROUP_ROWS).enumerate() {
        let base = chunk_index * ROW_GROUP_ROWS;
        let rows = chunk
            .iter()
            .enumerate()
            .map(|(index, sample)| Row::sample((base + index) as i64, sample))
            .collect::<Vec<_>>();
        writer.write(&batch_from_rows(schema.clone(), &capsule.manifest, &rows)?)?;
        flush_if_needed(&mut writer)?;
    }

    if !capsule.metrics.is_empty() {
        let rows = capsule
            .metrics
            .iter()
            .enumerate()
            .map(|(index, metric)| Row::metric(index as i64, metric))
            .collect::<Vec<_>>();
        writer.write(&batch_from_rows(schema, &capsule.manifest, &rows)?)?;
        flush_if_needed(&mut writer)?;
    }
    writer.close()?;

    let metadata = std::fs::metadata(path)?;
    Ok(CapsuleReceipt {
        schema_version: CAPSULE_SCHEMA_VERSION.to_owned(),
        run_id: capsule.manifest.run_id.clone(),
        sha256: sha256_file(path)?,
        size_bytes: metadata.len(),
        sample_count: capsule.samples.len(),
        metric_count: capsule.metrics.len(),
    })
}

fn flush_if_needed(writer: &mut ArrowWriter<File>) -> Result<()> {
    if writer.in_progress_size() >= FLUSH_MEMORY_BYTES {
        writer.flush()?;
    }
    Ok(())
}

#[derive(Clone, Copy)]
struct Row<'a> {
    record_kind: &'static str,
    ordinal: i64,
    sample: Option<&'a CapsuleSample>,
    metric: Option<&'a CapsuleMetric>,
}

impl<'a> Row<'a> {
    fn manifest() -> Self {
        Self { record_kind: "manifest", ordinal: 0, sample: None, metric: None }
    }

    fn sample(ordinal: i64, sample: &'a CapsuleSample) -> Self {
        Self { record_kind: "sample", ordinal, sample: Some(sample), metric: None }
    }

    fn metric(ordinal: i64, metric: &'a CapsuleMetric) -> Self {
        Self { record_kind: "metric", ordinal, sample: None, metric: Some(metric) }
    }
}

fn batch_from_rows(
    schema: Arc<Schema>,
    manifest: &CapsuleManifest,
    rows: &[Row<'_>],
) -> Result<RecordBatch> {
    let n = rows.len();
    let repeated = |value: &str| StringArray::from_iter_values((0..n).map(|_| value));
    let repeated_bool = |value: bool| BooleanArray::from_iter_values((0..n).map(|_| value));
    let repeated_optional_bool = |value: Option<bool>| BooleanArray::from((0..n).map(|_| value).collect::<Vec<_>>());

    let columns: Vec<ArrayRef> = vec![
        Arc::new(repeated(CAPSULE_SCHEMA_VERSION)),
        Arc::new(repeated(&manifest.run_id)),
        Arc::new(StringArray::from_iter_values(rows.iter().map(|row| row.record_kind))),
        Arc::new(Int64Array::from_iter_values(rows.iter().map(|row| row.ordinal))),
        Arc::new(repeated(&manifest.model_id)),
        Arc::new(repeated(&manifest.source_framework)),
        Arc::new(repeated(&manifest.source_revision)),
        Arc::new(repeated(&manifest.candidate_id)),
        Arc::new(repeated(&manifest.provider_id)),
        Arc::new(repeated(&manifest.decoder)),
        Arc::new(repeated(&manifest.environment_id)),
        Arc::new(repeated(&manifest.evaluation_input_id)),
        Arc::new(repeated(&manifest.git_commit)),
        Arc::new(repeated_bool(manifest.provider_registered)),
        Arc::new(repeated_optional_bool(manifest.provider_execution_proven)),
        Arc::new(repeated_optional_bool(manifest.provider_assignment_proven)),
        Arc::new(repeated_optional_bool(manifest.fallback_detected)),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.map(|s| s.sample_id.as_str())).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.map(|s| s.dataset_id.as_str())).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.map(|s| s.dataset_repo_id.as_str())).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.map(|s| s.dataset_revision.as_str())).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.map(|s| s.audio_sha256.as_str())).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.map(|s| s.audio_duration_sec)).collect::<Vec<_>>())),
        Arc::new(Int64Array::from(rows.iter().map(|row| row.sample.map(|s| i64::from(s.sample_rate_hz))).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.map(|s| s.reference_text.as_str())).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.map(|s| s.hypothesis_text.as_str())).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.map(|s| s.normalized_text.as_str())).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.and_then(|s| s.cer)).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.and_then(|s| s.wer)).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.and_then(|s| s.audio_decode_ms)).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.and_then(|s| s.resample_ms)).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.and_then(|s| s.inference_ms)).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.and_then(|s| s.decoder_ms)).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.and_then(|s| s.postprocess_ms)).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.map(|s| s.total_ms)).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.and_then(|s| s.rtf)).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.and_then(|s| s.peak_ram_mb)).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.sample.and_then(|s| s.peak_device_memory_mb)).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.map(|s| s.status.as_str())).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.and_then(|s| s.error_code.as_deref())).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.and_then(|s| s.error_stage.as_deref())).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.sample.and_then(|s| s.error_message.as_deref())).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.metric.map(|m| m.name.as_str())).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|row| row.metric.map(|m| m.value)).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|row| row.metric.and_then(|m| m.unit.as_deref())).collect::<Vec<_>>())),
    ];

    Ok(RecordBatch::try_new(schema, columns)?)
}
