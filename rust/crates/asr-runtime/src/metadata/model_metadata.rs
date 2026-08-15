use std::{fs, path::Path};
use serde::{Deserialize, Serialize};
use crate::error::{Result, RuntimeError};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum InputKind { CanonicalWaveform, Features }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DecoderKind { Ctc, Tdt }

fn default_decoder() -> DecoderKind { DecoderKind::Ctc }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeContract {
    pub input_kind: InputKind,
    pub primary_input: String,
    pub length_input: Option<String>,
    pub logits_output: String,
    pub blank_id: i64,
    #[serde(default = "default_decoder")]
    pub decoder: DecoderKind,
}

impl RuntimeContract {
    pub fn validate(&self) -> Result<()> {
        if self.primary_input.is_empty() || self.logits_output.is_empty() { return Err(RuntimeError::InvalidMetadata("runtime_contract input/output names must be non-empty".into())); }
        if self.blank_id < 0 { return Err(RuntimeError::InvalidMetadata("blank_id must be non-negative".into())); }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CandidateMetadata { pub runtime_contract: RuntimeContract }

impl CandidateMetadata {
    pub fn load(candidate_dir: impl AsRef<Path>) -> Result<Self> {
        let path = candidate_dir.as_ref().join("metadata.json");
        if !path.is_file() { return Err(RuntimeError::MetadataMissing(path)); }
        let text = fs::read_to_string(&path).map_err(|e| RuntimeError::InvalidMetadata(format!("{}: {e}", path.display())))?;
        let value: Self = serde_json::from_str(&text).map_err(|e| RuntimeError::InvalidMetadata(e.to_string()))?;
        value.runtime_contract.validate()?;
        Ok(value)
    }
}
