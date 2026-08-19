use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::path::Path;
use std::str::FromStr;

use arrow_array::{Array, Float64Array, Int64Array, RecordBatch, RecordBatchReader, StringArray};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

use crate::error::{CapsuleError, Result};
use crate::model::{
    CapsuleSummary, DEFAULT_ROW_GROUP_SIZE, EXPERIMENT_CAPSULE_SCHEMA_VERSION, RecordKind,
};
use crate::schema::experiment_capsule_v1_schema;

fn string_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a StringArray> {
    batch
        .column_by_name(name)
        .and_then(|array| array.as_any().downcast_ref::<StringArray>())
        .ok_or_else(|| CapsuleError::Contract(format!("missing Utf8 column: {name}")))
}

fn float64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a Float64Array> {
    batch
        .column_by_name(name)
        .and_then(|array| array.as_any().downcast_ref::<Float64Array>())
        .ok_or_else(|| CapsuleError::Contract(format!("missing Float64 column: {name}")))
}

fn int64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a Int64Array> {
    batch
        .column_by_name(name)
        .and_then(|array| array.as_any().downcast_ref::<Int64Array>())
        .ok_or_else(|| CapsuleError::Contract(format!("missing Int64 column: {name}")))
}

fn validate_arrow_schema(actual: &arrow_schema::Schema) -> Result<()> {
    let expected = experiment_capsule_v1_schema();
    if actual.fields().len() != expected.fields().len() {
        return Err(CapsuleError::Contract(format!(
            "capsule column count mismatch: expected={}, actual={}",
            expected.fields().len(),
            actual.fields().len()
        )));
    }
    for (actual, expected) in actual.fields().iter().zip(expected.fields()) {
        if actual.name() != expected.name() || actual.data_type() != expected.data_type() {
            return Err(CapsuleError::Contract(format!(
                "capsule schema mismatch at {}: expected={:?}, actual={:?}",
                expected.name(),
                expected.data_type(),
                actual.data_type()
            )));
        }
    }
    Ok(())
}

pub fn read_capsule_summary(path: impl AsRef<Path>) -> Result<CapsuleSummary> {
    let file = File::open(path)?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)?;
    let provenance_manifest_sha256 = builder
        .metadata()
        .file_metadata()
        .key_value_metadata()
        .and_then(|items| {
            items
                .iter()
                .find(|item| item.key == "jpapt.provenance.manifest_sha256")
        })
        .and_then(|item| item.value.clone());
    let mut reader = builder.with_batch_size(DEFAULT_ROW_GROUP_SIZE).build()?;
    let schema = reader.schema();
    validate_arrow_schema(schema.as_ref())?;

    let mut run_id: Option<String> = None;
    let mut row_count = 0usize;
    let mut sample_count = 0usize;
    let mut diagnostic_count = 0usize;
    let mut manifest_count = 0usize;
    let mut artifact_ids = BTreeSet::new();
    let mut metrics = BTreeMap::new();
    let mut expected_ordinal = 0i64;

    for batch in &mut reader {
        let batch = batch?;
        let schema_versions = string_column(&batch, "schema_version")?;
        let run_ids = string_column(&batch, "run_id")?;
        let record_kinds = string_column(&batch, "record_kind")?;
        let ordinals = int64_column(&batch, "ordinal")?;
        let metric_names = string_column(&batch, "metric_name")?;
        let metric_values = float64_column(&batch, "metric_value")?;
        let artifact_ids_column = string_column(&batch, "artifact_id")?;

        for index in 0..batch.num_rows() {
            if schema_versions.value(index) != EXPERIMENT_CAPSULE_SCHEMA_VERSION {
                return Err(CapsuleError::Contract(format!(
                    "unsupported schema version at row {row_count}: {}",
                    schema_versions.value(index)
                )));
            }

            let current_run_id = run_ids.value(index);
            match &run_id {
                Some(expected) if expected != current_run_id => {
                    return Err(CapsuleError::Contract(format!(
                        "multiple run IDs in capsule: {expected} and {current_run_id}"
                    )));
                }
                None => run_id = Some(current_run_id.to_owned()),
                _ => {}
            }

            let ordinal = ordinals.value(index);
            if ordinal != expected_ordinal {
                return Err(CapsuleError::Contract(format!(
                    "non-contiguous ordinal: expected={expected_ordinal}, actual={ordinal}"
                )));
            }
            expected_ordinal += 1;

            match RecordKind::from_str(record_kinds.value(index))? {
                RecordKind::Manifest => {
                    if ordinal != 0 {
                        return Err(CapsuleError::Contract(
                            "manifest row must have ordinal 0".into(),
                        ));
                    }
                    manifest_count += 1;
                }
                RecordKind::Sample => sample_count += 1,
                RecordKind::Diagnostic => diagnostic_count += 1,
                RecordKind::Artifact => {
                    if artifact_ids_column.is_null(index) {
                        return Err(CapsuleError::Contract(
                            "artifact row is missing artifact_id".into(),
                        ));
                    }
                    artifact_ids.insert(artifact_ids_column.value(index).to_owned());
                }
                RecordKind::Metric => {
                    if metric_names.is_null(index) {
                        return Err(CapsuleError::Contract(
                            "metric row is missing metric_name".into(),
                        ));
                    }
                    let name = metric_names.value(index).to_owned();
                    if !metric_values.is_null(index)
                        && metrics
                            .insert(name.clone(), metric_values.value(index))
                            .is_some()
                    {
                        return Err(CapsuleError::Contract(format!("duplicate metric: {name}")));
                    }
                }
            }
            row_count += 1;
        }
    }

    if row_count == 0 {
        return Err(CapsuleError::Contract("capsule contains no rows".into()));
    }
    if manifest_count != 1 {
        return Err(CapsuleError::Contract(format!(
            "capsule must contain exactly one manifest row; found {manifest_count}"
        )));
    }

    Ok(CapsuleSummary {
        run_id: run_id.ok_or_else(|| CapsuleError::Contract("capsule has no run_id".into()))?,
        row_count,
        sample_count,
        diagnostic_count,
        artifact_ids,
        metrics,
        provenance_manifest_sha256,
    })
}
