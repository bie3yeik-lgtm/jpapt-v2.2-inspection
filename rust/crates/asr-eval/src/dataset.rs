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
    #[serde(default)]
    pub tags: Vec<String>,
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
        if self.schema_version != 1 {
            return Err(format!(
                "unsupported schema_version {}",
                self.schema_version
            ));
        }
        if self.samples.len() != self.resolved_sample_count
            || self.samples.len() != self.expected_sample_count
        {
            return Err("resolved/expected sample counts disagree".into());
        }
        let mut ids = std::collections::HashSet::with_capacity(self.samples.len());
        if self.samples.iter().any(|sample| {
            !sample.duration_sec.is_finite()
                || sample.duration_sec <= 0.0
                || !ids.insert(sample.id.as_str())
        }) {
            return Err(
                "resolved manifest contains invalid duration or duplicate sample ID".into(),
            );
        }
        if self
            .samples
            .iter()
            .any(|s| s.audio_path.as_deref().is_none_or(str::is_empty))
        {
            return Err("every Rust evaluation sample must have materialized audio_path".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::{ResolvedManifest, ResolvedSample};

    fn sample(id: &str, duration_sec: f64) -> ResolvedSample {
        ResolvedSample {
            id: id.to_owned(),
            manifest_entry_id: "entry-001".into(),
            dataset_id: "dataset".into(),
            dataset_repo_id: "owner/dataset".into(),
            dataset_revision: "revision".into(),
            subset: None,
            split: Some("test".into()),
            row_index: 0,
            source_identity: id.into(),
            selection_hash: "hash".into(),
            selection_rank: 0,
            duration_sec,
            sample_rate_hz: Some(16_000),
            transcription: "text".into(),
            tags: vec![],
            audio_path: Some("/tmp/materialized.wav".into()),
            audio_sha256: None,
        }
    }

    #[test]
    fn rejects_duplicate_or_non_finite_samples() {
        let mut manifest = ResolvedManifest {
            schema_version: 1,
            manifest_path: "manifest.jsonl".into(),
            expected_sample_count: 2,
            resolved_sample_count: 2,
            samples: vec![sample("same", 1.0), sample("same", 1.0)],
        };
        assert!(manifest.validate().is_err());
        manifest.samples[1] = sample("other", f64::NAN);
        assert!(manifest.validate().is_err());
    }
}
