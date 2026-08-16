use std::{fs::File, path::Path, sync::Arc};

use anyhow::{Context, Result, bail};
use arrow_array::{
    Array, ArrayRef, Float64Array, RecordBatch, StringArray, UInt32Array, UInt64Array,
};
use arrow_schema::{DataType, Field, Schema};
use parquet::{
    arrow::{ArrowWriter, arrow_reader::ParquetRecordBatchReaderBuilder},
    basic::Compression,
    file::properties::WriterProperties,
};

use crate::model::{EVALUATION_INPUT_SCHEMA_VERSION, EvaluationInputSet, MaterializedSample};

const BATCH_SIZE: usize = 512;

pub fn evaluation_input_parquet_schema() -> Arc<Schema> {
    Arc::new(Schema::new(vec![
        Field::new("schema_version", DataType::UInt32, false),
        Field::new("input_id", DataType::Utf8, false),
        Field::new("id", DataType::Utf8, false),
        Field::new("manifest_entry_id", DataType::Utf8, false),
        Field::new("dataset_id", DataType::Utf8, false),
        Field::new("dataset_repo_id", DataType::Utf8, false),
        Field::new("dataset_revision", DataType::Utf8, false),
        Field::new("subset", DataType::Utf8, true),
        Field::new("split", DataType::Utf8, true),
        Field::new("row_index", DataType::UInt64, false),
        Field::new("source_identity", DataType::Utf8, false),
        Field::new("selection_hash", DataType::Utf8, false),
        Field::new("selection_rank", DataType::UInt64, false),
        Field::new("duration_sec", DataType::Float64, false),
        Field::new("sample_rate_hz", DataType::UInt32, false),
        Field::new("transcription", DataType::Utf8, false),
        Field::new("tags_json", DataType::Utf8, false),
        Field::new("audio_path", DataType::Utf8, false),
        Field::new("audio_sha256", DataType::Utf8, false),
    ]))
}

pub fn write_parquet_input(path: impl AsRef<Path>, input: &EvaluationInputSet) -> Result<()> {
    input.validate()?;
    let path = path.as_ref();
    let file = File::create(path)
        .with_context(|| format!("failed to create Parquet input {}", path.display()))?;
    let schema = evaluation_input_parquet_schema();
    let props = WriterProperties::builder()
        .set_compression(Compression::ZSTD(Default::default()))
        .set_max_row_group_size(BATCH_SIZE)
        .build();
    let mut writer = ArrowWriter::try_new(file, schema.clone(), Some(props))?;

    for samples in input.samples.chunks(BATCH_SIZE) {
        writer.write(&build_batch(schema.clone(), input, samples)?)?;
        if writer.in_progress_size() > 16 * 1024 * 1024 {
            writer.flush()?;
        }
    }
    writer.close()?;
    Ok(())
}

pub fn load_parquet_input(path: impl AsRef<Path>) -> Result<EvaluationInputSet> {
    let path = path.as_ref();
    let file = File::open(path)
        .with_context(|| format!("failed to open Parquet input {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)?;
    let observed = builder.schema().clone();
    let expected = evaluation_input_parquet_schema();
    if observed.as_ref() != expected.as_ref() {
        bail!("Parquet evaluation input schema does not exactly match canonical schema v2");
    }

    let reader = builder.with_batch_size(BATCH_SIZE).build()?;
    let mut samples = Vec::new();
    let mut input_id: Option<String> = None;

    for batch in reader {
        let batch = batch?;
        for row in 0..batch.num_rows() {
            let schema_version = required_u32(&batch, "schema_version", row)?;
            if schema_version != EVALUATION_INPUT_SCHEMA_VERSION {
                bail!("Parquet row {row} has unsupported schema_version {schema_version}");
            }
            let row_input_id = required_string(&batch, "input_id", row)?;
            match &input_id {
                Some(expected) if expected != row_input_id => {
                    bail!("Parquet input contains multiple input_id values")
                }
                None => input_id = Some(row_input_id.to_owned()),
                _ => {}
            }

            let tags_json = required_string(&batch, "tags_json", row)?;
            let tags: Vec<String> = serde_json::from_str(tags_json)
                .with_context(|| format!("invalid tags_json at Parquet row {row}"))?;
            samples.push(MaterializedSample {
                id: required_string(&batch, "id", row)?.to_owned(),
                manifest_entry_id: required_string(&batch, "manifest_entry_id", row)?.to_owned(),
                dataset_id: required_string(&batch, "dataset_id", row)?.to_owned(),
                dataset_repo_id: required_string(&batch, "dataset_repo_id", row)?.to_owned(),
                dataset_revision: required_string(&batch, "dataset_revision", row)?.to_owned(),
                subset: optional_string(&batch, "subset", row)?.map(str::to_owned),
                split: optional_string(&batch, "split", row)?.map(str::to_owned),
                row_index: required_u64(&batch, "row_index", row)?,
                source_identity: required_string(&batch, "source_identity", row)?.to_owned(),
                selection_hash: required_string(&batch, "selection_hash", row)?.to_owned(),
                selection_rank: required_u64(&batch, "selection_rank", row)?,
                duration_sec: required_f64(&batch, "duration_sec", row)?,
                sample_rate_hz: required_u32(&batch, "sample_rate_hz", row)?,
                transcription: required_string(&batch, "transcription", row)?.to_owned(),
                tags,
                audio_path: required_string(&batch, "audio_path", row)?.to_owned(),
                audio_sha256: required_string(&batch, "audio_sha256", row)?.to_owned(),
            });
        }
    }

    let input = EvaluationInputSet {
        schema_version: EVALUATION_INPUT_SCHEMA_VERSION,
        input_id: input_id.ok_or_else(|| anyhow::anyhow!("Parquet evaluation input is empty"))?,
        expected_sample_count: samples.len(),
        samples,
    };
    input.validate()?;
    Ok(input)
}

fn build_batch(
    schema: Arc<Schema>,
    input: &EvaluationInputSet,
    samples: &[MaterializedSample],
) -> Result<RecordBatch> {
    let schema_versions = UInt32Array::from(vec![EVALUATION_INPUT_SCHEMA_VERSION; samples.len()]);
    let input_ids = StringArray::from_iter_values((0..samples.len()).map(|_| input.input_id.as_str()));
    let tags = samples
        .iter()
        .map(|sample| serde_json::to_string(&sample.tags))
        .collect::<std::result::Result<Vec<_>, _>>()?;

    let columns: Vec<ArrayRef> = vec![
        Arc::new(schema_versions),
        Arc::new(input_ids),
        Arc::new(StringArray::from_iter_values(samples.iter().map(|s| s.id.as_str()))),
        Arc::new(StringArray::from_iter_values(samples.iter().map(|s| s.manifest_entry_id.as_str()))),
        Arc::new(StringArray::from_iter_values(samples.iter().map(|s| s.dataset_id.as_str()))),
        Arc::new(StringArray::from_iter_values(samples.iter().map(|s| s.dataset_repo_id.as_str()))),
        Arc::new(StringArray::from_iter_values(samples.iter().map(|s| s.dataset_revision.as_str()))),
        Arc::new(StringArray::from(samples.iter().map(|s| s.subset.as_deref()).collect::<Vec<_>>())),
        Arc::new(StringArray::from(samples.iter().map(|s| s.split.as_deref()).collect::<Vec<_>>())),
        Arc::new(UInt64Array::from_iter_values(samples.iter().map(|s| s.row_index))),
        Arc::new(StringArray::from_iter_values(samples.iter().map(|s| s.source_identity.as_str()))),
        Arc::new(StringArray::from_iter_values(samples.iter().map(|s| s.selection_hash.as_str()))),
        Arc::new(UInt64Array::from_iter_values(samples.iter().map(|s| s.selection_rank))),
        Arc::new(Float64Array::from_iter_values(samples.iter().map(|s| s.duration_sec))),
        Arc::new(UInt32Array::from_iter_values(samples.iter().map(|s| s.sample_rate_hz))),
        Arc::new(StringArray::from_iter_values(samples.iter().map(|s| s.transcription.as_str()))),
        Arc::new(StringArray::from_iter_values(tags.iter().map(String::as_str))),
        Arc::new(StringArray::from_iter_values(samples.iter().map(|s| s.audio_path.as_str()))),
        Arc::new(StringArray::from_iter_values(samples.iter().map(|s| s.audio_sha256.as_str()))),
    ];
    Ok(RecordBatch::try_new(schema, columns)?)
}

fn column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a ArrayRef> {
    let index = batch.schema().index_of(name)?;
    Ok(batch.column(index))
}

fn required_string<'a>(batch: &'a RecordBatch, name: &str, row: usize) -> Result<&'a str> {
    let array = column(batch, name)?
        .as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| anyhow::anyhow!("column {name} is not Utf8"))?;
    if array.is_null(row) {
        bail!("column {name} is null at row {row}");
    }
    Ok(array.value(row))
}

fn optional_string<'a>(batch: &'a RecordBatch, name: &str, row: usize) -> Result<Option<&'a str>> {
    let array = column(batch, name)?
        .as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| anyhow::anyhow!("column {name} is not Utf8"))?;
    Ok((!array.is_null(row)).then(|| array.value(row)))
}

fn required_u32(batch: &RecordBatch, name: &str, row: usize) -> Result<u32> {
    let array = column(batch, name)?
        .as_any()
        .downcast_ref::<UInt32Array>()
        .ok_or_else(|| anyhow::anyhow!("column {name} is not UInt32"))?;
    if array.is_null(row) { bail!("column {name} is null at row {row}"); }
    Ok(array.value(row))
}

fn required_u64(batch: &RecordBatch, name: &str, row: usize) -> Result<u64> {
    let array = column(batch, name)?
        .as_any()
        .downcast_ref::<UInt64Array>()
        .ok_or_else(|| anyhow::anyhow!("column {name} is not UInt64"))?;
    if array.is_null(row) { bail!("column {name} is null at row {row}"); }
    Ok(array.value(row))
}

fn required_f64(batch: &RecordBatch, name: &str, row: usize) -> Result<f64> {
    let array = column(batch, name)?
        .as_any()
        .downcast_ref::<Float64Array>()
        .ok_or_else(|| anyhow::anyhow!("column {name} is not Float64"))?;
    if array.is_null(row) { bail!("column {name} is null at row {row}"); }
    let value = array.value(row);
    if !value.is_finite() { bail!("column {name} must be finite at row {row}"); }
    Ok(value)
}

#[cfg(test)]
mod tests {
    use std::{env, fs};

    use super::*;

    fn fixture() -> EvaluationInputSet {
        EvaluationInputSet {
            schema_version: EVALUATION_INPUT_SCHEMA_VERSION,
            input_id: "fixture".into(),
            expected_sample_count: 1,
            samples: vec![MaterializedSample {
                id: "s1".into(), manifest_entry_id: "m1".into(), dataset_id: "d1".into(),
                dataset_repo_id: "org/repo".into(), dataset_revision: "revision".into(),
                subset: None, split: Some("test".into()), row_index: 0,
                source_identity: "source".into(), selection_hash: "selection".into(),
                selection_rank: 0, duration_sec: 1.25, sample_rate_hz: 16_000,
                transcription: "hello".into(), tags: vec!["fixture".into()],
                audio_path: "/tmp/audio.wav".into(),
                audio_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".into(),
            }],
        }
    }

    #[test]
    fn parquet_round_trip_is_semantic() {
        let path = env::temp_dir().join(format!("asr-input-{}.parquet", std::process::id()));
        let input = fixture();
        write_parquet_input(&path, &input).unwrap();
        let observed = load_parquet_input(&path).unwrap();
        fs::remove_file(path).ok();
        assert_eq!(observed, input);
    }
}
