use std::collections::HashSet;

use anyhow::{Result, bail};
use serde::{Deserialize, Serialize};

pub const EVALUATION_INPUT_SCHEMA_VERSION: u32 = 2;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct MaterializedSample {
    pub id: String,
    pub manifest_entry_id: String,
    pub dataset_id: String,
    pub dataset_repo_id: String,
    pub dataset_revision: String,
    pub subset: Option<String>,
    pub split: Option<String>,
    pub row_index: u64,
    pub source_identity: String,
    pub selection_hash: String,
    pub selection_rank: u64,
    pub duration_sec: f64,
    pub sample_rate_hz: u32,
    pub transcription: String,
    #[serde(default)]
    pub tags: Vec<String>,
    pub audio_path: String,
    pub audio_sha256: String,
}

impl MaterializedSample {
    pub fn validate(&self) -> Result<()> {
        for (name, value) in [
            ("id", self.id.as_str()),
            ("manifest_entry_id", self.manifest_entry_id.as_str()),
            ("dataset_id", self.dataset_id.as_str()),
            ("dataset_repo_id", self.dataset_repo_id.as_str()),
            ("dataset_revision", self.dataset_revision.as_str()),
            ("source_identity", self.source_identity.as_str()),
            ("selection_hash", self.selection_hash.as_str()),
            ("audio_path", self.audio_path.as_str()),
            ("audio_sha256", self.audio_sha256.as_str()),
        ] {
            if value.trim().is_empty() || value != value.trim() {
                bail!("sample {} field {name} must be non-empty and trimmed", self.id);
            }
        }
        if !self.duration_sec.is_finite() || self.duration_sec <= 0.0 {
            bail!("sample {} duration_sec must be finite and positive", self.id);
        }
        if self.sample_rate_hz == 0 {
            bail!("sample {} sample_rate_hz must be positive", self.id);
        }
        if self.audio_sha256.len() != 64
            || !self
                .audio_sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            bail!("sample {} audio_sha256 must be lowercase SHA-256", self.id);
        }
        if self.tags.iter().any(|tag| tag.trim().is_empty() || tag != tag.trim()) {
            bail!("sample {} tags must be non-empty and trimmed", self.id);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct EvaluationInputSet {
    pub schema_version: u32,
    pub input_id: String,
    pub expected_sample_count: usize,
    pub samples: Vec<MaterializedSample>,
}

impl EvaluationInputSet {
    pub fn validate(&self) -> Result<()> {
        if self.schema_version != EVALUATION_INPUT_SCHEMA_VERSION {
            bail!(
                "unsupported evaluation input schema_version {}; expected {}",
                self.schema_version,
                EVALUATION_INPUT_SCHEMA_VERSION
            );
        }
        if self.input_id.trim().is_empty() || self.input_id != self.input_id.trim() {
            bail!("input_id must be non-empty and trimmed");
        }
        if self.samples.len() != self.expected_sample_count {
            bail!(
                "expected_sample_count {} does not match samples {}",
                self.expected_sample_count,
                self.samples.len()
            );
        }
        if self.samples.is_empty() {
            bail!("evaluation input must contain at least one sample");
        }

        let mut ids = HashSet::with_capacity(self.samples.len());
        for sample in &self.samples {
            sample.validate()?;
            if !ids.insert(sample.id.as_str()) {
                bail!("duplicate sample id {}", sample.id);
            }
        }
        Ok(())
    }
}
