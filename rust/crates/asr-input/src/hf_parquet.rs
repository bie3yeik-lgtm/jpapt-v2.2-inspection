use std::{fs, path::{Path, PathBuf}};

use anyhow::{Context, Result, bail};
use arrow_array::{Array, BinaryArray, LargeBinaryArray, LargeStringArray, RecordBatch, StringArray, StructArray};
use asr_audio::decode_audio;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::model::{EVALUATION_INPUT_SCHEMA_VERSION, EvaluationInputSet, MaterializedSample};

pub const HF_AUDIO_PARQUET_SPEC_VERSION: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HfAudioParquetSpec {
    pub schema_version: u32,
    pub input_id: String,
    pub dataset_id: String,
    pub dataset_repo_id: String,
    pub dataset_revision: String,
    pub subset: Option<String>,
    pub split: String,
    pub parquet_path: PathBuf,
    pub audio_column: String,
    pub text_column: String,
    pub materialized_root: PathBuf,
    pub sample_limit: Option<usize>,
}

impl HfAudioParquetSpec {
    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref();
        let value: Self = serde_json::from_str(&fs::read_to_string(path)?)?;
        value.validate()?;
        Ok(value)
    }

    pub fn validate(&self) -> Result<()> {
        if self.schema_version != HF_AUDIO_PARQUET_SPEC_VERSION {
            bail!("unsupported HF Audio Parquet spec schema_version {}", self.schema_version);
        }
        for (name, value) in [
            ("input_id", self.input_id.as_str()),
            ("dataset_id", self.dataset_id.as_str()),
            ("dataset_repo_id", self.dataset_repo_id.as_str()),
            ("dataset_revision", self.dataset_revision.as_str()),
            ("split", self.split.as_str()),
            ("audio_column", self.audio_column.as_str()),
            ("text_column", self.text_column.as_str()),
        ] {
            if value.trim().is_empty() || value != value.trim() {
                bail!("{name} must be non-empty and trimmed");
            }
        }
        if self.dataset_revision.len() < 40
            || self.dataset_revision.len() > 64
            || !self
                .dataset_revision
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            bail!("dataset_revision must be an immutable lowercase hexadecimal Hub revision");
        }
        if self.sample_limit == Some(0) {
            bail!("sample_limit must be positive when specified");
        }
        Ok(())
    }
}

pub fn materialize_hf_audio_parquet(spec: &HfAudioParquetSpec) -> Result<EvaluationInputSet> {
    spec.validate()?;
    fs::create_dir_all(&spec.materialized_root).with_context(|| {
        format!(
            "failed to create materialization root {}",
            spec.materialized_root.display()
        )
    })?;

    let file = fs::File::open(&spec.parquet_path)
        .with_context(|| format!("failed to open {}", spec.parquet_path.display()))?;
    let reader = ParquetRecordBatchReaderBuilder::try_new(file)?
        .with_batch_size(128)
        .build()?;

    let mut samples = Vec::new();
    let mut global_row = 0_u64;
    'batches: for batch in reader {
        let batch = batch?;
        let audio = struct_column(&batch, &spec.audio_column)?;
        let text = batch
            .column(batch.schema().index_of(&spec.text_column)?)
            .clone();
        let bytes = audio
            .column_by_name("bytes")
            .ok_or_else(|| anyhow::anyhow!("HF Audio struct has no bytes child"))?;
        let source_path = audio.column_by_name("path");

        for row in 0..batch.num_rows() {
            if spec.sample_limit.is_some_and(|limit| samples.len() >= limit) {
                break 'batches;
            }
            if audio.is_null(row) {
                bail!("audio column is null at source row {global_row}");
            }
            let audio_bytes = binary_value(bytes.as_ref(), row)?;
            if audio_bytes.is_empty() {
                bail!("audio bytes are empty at source row {global_row}");
            }
            let transcription = string_value(text.as_ref(), row, &spec.text_column)?;
            let extension = source_path
                .as_ref()
                .and_then(|array| optional_string_value(array.as_ref(), row).transpose())
                .transpose()?
                .and_then(safe_extension)
                .unwrap_or("audio");
            let local_path = spec
                .materialized_root
                .join(format!("sample-{global_row:08}.{extension}"));
            write_immutable(&local_path, audio_bytes)?;

            let decoded = decode_audio(&local_path).with_context(|| {
                format!("failed to decode materialized HF audio {}", local_path.display())
            })?;
            let duration_sec = decoded.frames() as f64 / f64::from(decoded.sample_rate_hz);
            if !duration_sec.is_finite() || duration_sec <= 0.0 {
                bail!("decoded duration is invalid at source row {global_row}");
            }
            let audio_sha256 = sha256_bytes(audio_bytes);
            let source_identity = format!(
                "hf://datasets/{}@{}/{}/{}#{}",
                spec.dataset_repo_id,
                spec.dataset_revision,
                spec.subset.as_deref().unwrap_or("default"),
                spec.split,
                global_row
            );
            let selection_hash = sha256_bytes(source_identity.as_bytes());
            let sample_id = format!("{}:{}:{global_row}", spec.dataset_id, spec.split);

            samples.push(MaterializedSample {
                id: sample_id.clone(),
                manifest_entry_id: sample_id,
                dataset_id: spec.dataset_id.clone(),
                dataset_repo_id: spec.dataset_repo_id.clone(),
                dataset_revision: spec.dataset_revision.clone(),
                subset: spec.subset.clone(),
                split: Some(spec.split.clone()),
                row_index: global_row,
                source_identity,
                selection_hash,
                selection_rank: samples.len() as u64,
                duration_sec,
                sample_rate_hz: decoded.sample_rate_hz,
                transcription: transcription.to_owned(),
                tags: vec!["hf-parquet-audio".to_owned()],
                audio_path: local_path.to_string_lossy().into_owned(),
                audio_sha256,
            });
            global_row += 1;
        }
    }

    let input = EvaluationInputSet {
        schema_version: EVALUATION_INPUT_SCHEMA_VERSION,
        input_id: spec.input_id.clone(),
        expected_sample_count: samples.len(),
        samples,
    };
    input.validate()?;
    Ok(input)
}

fn struct_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a StructArray> {
    batch
        .column(batch.schema().index_of(name)?)
        .as_any()
        .downcast_ref::<StructArray>()
        .ok_or_else(|| anyhow::anyhow!("column {name} must be a Struct audio column"))
}

fn binary_value(array: &dyn Array, row: usize) -> Result<&[u8]> {
    if let Some(array) = array.as_any().downcast_ref::<BinaryArray>() {
        if array.is_null(row) { bail!("audio.bytes is null at row {row}"); }
        return Ok(array.value(row));
    }
    if let Some(array) = array.as_any().downcast_ref::<LargeBinaryArray>() {
        if array.is_null(row) { bail!("audio.bytes is null at row {row}"); }
        return Ok(array.value(row));
    }
    bail!("audio.bytes must be Binary or LargeBinary")
}

fn string_value<'a>(array: &'a dyn Array, row: usize, name: &str) -> Result<&'a str> {
    optional_string_value(array, row)?.ok_or_else(|| anyhow::anyhow!("column {name} is null at row {row}"))
}

fn optional_string_value(array: &dyn Array, row: usize) -> Result<Option<&str>> {
    if let Some(array) = array.as_any().downcast_ref::<StringArray>() {
        return Ok((!array.is_null(row)).then(|| array.value(row)));
    }
    if let Some(array) = array.as_any().downcast_ref::<LargeStringArray>() {
        return Ok((!array.is_null(row)).then(|| array.value(row)));
    }
    bail!("string column must be Utf8 or LargeUtf8")
}

fn safe_extension(path: &str) -> Option<&str> {
    let extension = Path::new(path).extension()?.to_str()?;
    (!extension.is_empty()
        && extension.len() <= 8
        && extension.bytes().all(|byte| byte.is_ascii_alphanumeric()))
        .then_some(extension)
}

fn write_immutable(path: &Path, bytes: &[u8]) -> Result<()> {
    if path.exists() {
        let observed = fs::read(path)?;
        if sha256_bytes(&observed) != sha256_bytes(bytes) {
            bail!("materialized path already exists with different content: {}", path.display());
        }
        return Ok(());
    }
    fs::write(path, bytes)?;
    Ok(())
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
