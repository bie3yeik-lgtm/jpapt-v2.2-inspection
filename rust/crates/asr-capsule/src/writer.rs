use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use arrow_array::{
    ArrayRef, BinaryArray, Float64Array, Int32Array, Int64Array, RecordBatch, StringArray,
};
use arrow_schema::DataType;
use parquet::arrow::ArrowWriter;
use parquet::basic::{Compression, ZstdLevel};
use parquet::file::metadata::KeyValue;
use parquet::file::properties::WriterProperties;
use serde_json::Value;
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::error::{CapsuleError, Result};
use crate::model::{
    CapsuleReceipt, CapsuleRow, CapsuleValue, DEFAULT_ROW_GROUP_SIZE,
    EXPERIMENT_CAPSULE_SCHEMA_VERSION,
};
use crate::reader::read_capsule_summary;
use crate::schema::experiment_capsule_v1_schema;

pub const CAPSULE_WRITER_VERSION: &str = "rust-arrow-parquet/v1";

fn temporary_path(destination: &Path) -> PathBuf {
    let name = destination
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("run.parquet");
    destination.with_file_name(format!(".{name}.{}.tmp", Uuid::new_v4()))
}

fn sha256_file(path: &Path) -> Result<String> {
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn field_value<'a>(row: &'a CapsuleRow, name: &str) -> Option<&'a CapsuleValue> {
    row.field(name)
}

fn string_value<'a>(row: &'a CapsuleRow, name: &str) -> Result<Option<&'a str>> {
    match name {
        "schema_version" => Ok(Some(EXPERIMENT_CAPSULE_SCHEMA_VERSION)),
        "run_id" => Ok(Some(row.run_id.as_str())),
        "record_kind" => Ok(Some(row.record_kind.as_str())),
        _ => match field_value(row, name) {
            Some(CapsuleValue::String(value)) => Ok(Some(value.as_str())),
            None => Ok(None),
            Some(_) => Err(CapsuleError::Contract(format!(
                "field {name} has the wrong capsule value type"
            ))),
        },
    }
}

fn float64_value(row: &CapsuleRow, name: &str) -> Result<Option<f64>> {
    match field_value(row, name) {
        Some(CapsuleValue::Float64(value)) => Ok(Some(*value)),
        None => Ok(None),
        Some(_) => Err(CapsuleError::Contract(format!(
            "field {name} has the wrong capsule value type"
        ))),
    }
}

fn int32_value(row: &CapsuleRow, name: &str) -> Result<Option<i32>> {
    match field_value(row, name) {
        Some(CapsuleValue::Int32(value)) => Ok(Some(*value)),
        None => Ok(None),
        Some(_) => Err(CapsuleError::Contract(format!(
            "field {name} has the wrong capsule value type"
        ))),
    }
}

fn int64_value(row: &CapsuleRow, name: &str) -> Result<Option<i64>> {
    if name == "ordinal" {
        return Ok(Some(row.ordinal));
    }
    match field_value(row, name) {
        Some(CapsuleValue::Int64(value)) => Ok(Some(*value)),
        None => Ok(None),
        Some(_) => Err(CapsuleError::Contract(format!(
            "field {name} has the wrong capsule value type"
        ))),
    }
}

fn binary_value<'a>(row: &'a CapsuleRow, name: &str) -> Result<Option<&'a [u8]>> {
    match field_value(row, name) {
        Some(CapsuleValue::Binary(value)) => Ok(Some(value.as_slice())),
        None => Ok(None),
        Some(_) => Err(CapsuleError::Contract(format!(
            "field {name} has the wrong capsule value type"
        ))),
    }
}

fn provenance_manifest_sha256(rows: &[CapsuleRow]) -> Result<Option<String>> {
    let Some(manifest) = rows
        .iter()
        .find(|row| row.record_kind == crate::model::RecordKind::Manifest)
    else {
        return Ok(None);
    };
    let Some(CapsuleValue::String(metadata)) = manifest.field("metadata_json") else {
        return Ok(None);
    };
    let value: Value = serde_json::from_str(metadata)?;
    Ok(value
        .pointer("/run_context/metadata/provenance/manifest_sha256")
        .and_then(Value::as_str)
        .map(str::to_owned))
}

pub fn rows_to_record_batch(rows: &[CapsuleRow]) -> Result<RecordBatch> {
    if rows.is_empty() {
        return Err(CapsuleError::Contract(
            "cannot create a RecordBatch from zero rows".into(),
        ));
    }

    let schema = experiment_capsule_v1_schema();
    let mut columns: Vec<ArrayRef> = Vec::with_capacity(schema.fields().len());

    for field in schema.fields() {
        let name = field.name();
        let array: ArrayRef = match field.data_type() {
            DataType::Utf8 => {
                let values = rows
                    .iter()
                    .map(|row| string_value(row, name))
                    .collect::<Result<Vec<_>>>()?;
                Arc::new(StringArray::from(values))
            }
            DataType::Float64 => {
                let values = rows
                    .iter()
                    .map(|row| float64_value(row, name))
                    .collect::<Result<Vec<_>>>()?;
                Arc::new(Float64Array::from(values))
            }
            DataType::Int32 => {
                let values = rows
                    .iter()
                    .map(|row| int32_value(row, name))
                    .collect::<Result<Vec<_>>>()?;
                Arc::new(Int32Array::from(values))
            }
            DataType::Int64 => {
                let values = rows
                    .iter()
                    .map(|row| int64_value(row, name))
                    .collect::<Result<Vec<_>>>()?;
                Arc::new(Int64Array::from(values))
            }
            DataType::Binary => {
                let values = rows
                    .iter()
                    .map(|row| binary_value(row, name))
                    .collect::<Result<Vec<_>>>()?;
                Arc::new(BinaryArray::from(values))
            }
            other => {
                return Err(CapsuleError::Contract(format!(
                    "unsupported Arrow type in ExperimentCapsuleV1: {other:?}"
                )));
            }
        };
        columns.push(array);
    }

    Ok(RecordBatch::try_new(schema, columns)?)
}

pub fn write_capsule(
    path: impl AsRef<Path>,
    run_id: &str,
    rows: &[CapsuleRow],
) -> Result<CapsuleReceipt> {
    if run_id.is_empty() {
        return Err(CapsuleError::Contract("run_id must not be empty".into()));
    }
    if rows.is_empty() {
        return Err(CapsuleError::Contract("capsule must contain rows".into()));
    }
    for row in rows {
        if row.run_id != run_id {
            return Err(CapsuleError::Contract(format!(
                "row run_id {} does not match capsule run_id {run_id}",
                row.run_id
            )));
        }
    }

    let destination = path.as_ref();
    if let Some(parent) = destination.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let temporary = temporary_path(destination);

    let result = (|| -> Result<CapsuleReceipt> {
        let properties = WriterProperties::builder()
            .set_compression(Compression::ZSTD(ZstdLevel::try_new(3)?))
            .set_max_row_group_row_count(Some(DEFAULT_ROW_GROUP_SIZE))
            .build();
        let file = File::create(&temporary)?;
        let mut writer =
            ArrowWriter::try_new(file, experiment_capsule_v1_schema(), Some(properties))?;
        writer.append_key_value_metadata(KeyValue {
            key: "jpapt.capsule.schema".into(),
            value: Some(EXPERIMENT_CAPSULE_SCHEMA_VERSION.into()),
        });
        if let Some(fingerprint) = provenance_manifest_sha256(rows)? {
            writer.append_key_value_metadata(KeyValue {
                key: "jpapt.provenance.manifest_sha256".into(),
                value: Some(fingerprint),
            });
        }
        writer.append_key_value_metadata(KeyValue {
            key: "jpapt.run_id".into(),
            value: Some(run_id.into()),
        });
        writer.append_key_value_metadata(KeyValue {
            key: "jpapt.writer".into(),
            value: Some(CAPSULE_WRITER_VERSION.into()),
        });

        for chunk in rows.chunks(DEFAULT_ROW_GROUP_SIZE) {
            writer.write(&rows_to_record_batch(chunk)?)?;
        }
        writer.sync()?;
        writer.close()?;
        File::options().write(true).open(&temporary)?.sync_all()?;

        let summary = read_capsule_summary(&temporary)?;
        if summary.run_id != run_id {
            return Err(CapsuleError::Contract(
                "written capsule run_id failed verification".into(),
            ));
        }
        let sha256 = sha256_file(&temporary)?;
        let size_bytes = std::fs::metadata(&temporary)?.len();
        std::fs::rename(&temporary, destination)?;
        Ok(CapsuleReceipt {
            path: destination.to_path_buf(),
            sha256,
            size_bytes,
            run_id: run_id.to_owned(),
        })
    })();

    if result.is_err() {
        let _ = std::fs::remove_file(&temporary);
    }
    result
}
