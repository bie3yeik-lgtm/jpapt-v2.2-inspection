use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResolvedSample {
    pub id: String,
    pub manifest_entry_id: String,
    pub dataset_id: String,
    pub dataset_repo_id: String,
    pub dataset_revision: String,
    pub subset: Option<String>,
    pub split: Option<String>,
    pub row_index: usize,
    pub source_identity: String,
    pub selection_hash: String,
    pub selection_rank: usize,
    pub duration_sec: f64,
    pub sample_rate_hz: Option<u32>,
    pub transcription: String,
    #[serde(default)] pub tags: Vec<String>,
    pub audio_path: Option<String>,
    pub audio_sha256: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResolvedManifest {
    pub schema_version: u32,
    pub manifest_path: String,
    pub expected_sample_count: usize,
    pub resolved_sample_count: usize,
    pub samples: Vec<ResolvedSample>,
}

impl ResolvedManifest {
    pub fn validate(&self) -> Result<(), String> {
        if self.schema_version != 1 { return Err(format!("unsupported schema_version {}", self.schema_version)); }
        if self.samples.len() != self.resolved_sample_count || self.samples.len() != self.expected_sample_count { return Err("resolved/expected sample counts disagree".into()); }
        if self.samples.iter().any(|s| s.audio_path.as_deref().is_none_or(str::is_empty)) { return Err("every Rust evaluation sample must have materialized audio_path".into()); }
        Ok(())
    }
}
