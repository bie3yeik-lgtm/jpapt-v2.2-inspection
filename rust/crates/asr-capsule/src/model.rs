use anyhow::{Result, bail};
use serde::{Deserialize, Serialize};

pub const CAPSULE_SCHEMA_VERSION: &str = "jpapt.experiment-capsule.v1";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CapsuleManifest {
    pub run_id: String,
    pub model_id: String,
    pub source_framework: String,
    pub source_revision: String,
    pub candidate_id: String,
    pub provider_id: String,
    pub decoder: String,
    pub environment_id: String,
    pub evaluation_input_id: String,
    pub git_commit: String,
    pub provider_registered: bool,
    pub provider_execution_proven: Option<bool>,
    pub provider_assignment_proven: Option<bool>,
    pub fallback_detected: Option<bool>,
}

impl CapsuleManifest {
    pub fn validate(&self) -> Result<()> {
        for (name, value) in [
            ("run_id", self.run_id.as_str()),
            ("model_id", self.model_id.as_str()),
            ("source_framework", self.source_framework.as_str()),
            ("source_revision", self.source_revision.as_str()),
            ("candidate_id", self.candidate_id.as_str()),
            ("provider_id", self.provider_id.as_str()),
            ("decoder", self.decoder.as_str()),
            ("environment_id", self.environment_id.as_str()),
            ("evaluation_input_id", self.evaluation_input_id.as_str()),
            ("git_commit", self.git_commit.as_str()),
        ] {
            if value.trim().is_empty() || value != value.trim() {
                bail!("capsule manifest {name} must be non-empty and trimmed");
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CapsuleSample {
    pub sample_id: String,
    pub dataset_id: String,
    pub dataset_repo_id: String,
    pub dataset_revision: String,
    pub audio_sha256: String,
    pub audio_duration_sec: f64,
    pub sample_rate_hz: u32,
    pub reference_text: String,
    pub hypothesis_text: String,
    pub normalized_text: String,
    pub cer: Option<f64>,
    pub wer: Option<f64>,
    pub audio_decode_ms: Option<f64>,
    pub resample_ms: Option<f64>,
    pub inference_ms: Option<f64>,
    pub decoder_ms: Option<f64>,
    pub postprocess_ms: Option<f64>,
    pub total_ms: f64,
    pub rtf: Option<f64>,
    pub peak_ram_mb: Option<f64>,
    pub peak_device_memory_mb: Option<f64>,
    pub status: String,
    pub error_code: Option<String>,
    pub error_stage: Option<String>,
    pub error_message: Option<String>,
}

impl CapsuleSample {
    pub fn validate(&self) -> Result<()> {
        for (name, value) in [
            ("sample_id", self.sample_id.as_str()),
            ("dataset_id", self.dataset_id.as_str()),
            ("dataset_repo_id", self.dataset_repo_id.as_str()),
            ("dataset_revision", self.dataset_revision.as_str()),
            ("audio_sha256", self.audio_sha256.as_str()),
            ("status", self.status.as_str()),
        ] {
            if value.trim().is_empty() || value != value.trim() {
                bail!("capsule sample {name} must be non-empty and trimmed");
            }
        }
        if self.audio_sha256.len() != 64
            || !self
                .audio_sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            bail!("audio_sha256 must be lowercase SHA-256");
        }
        if self.sample_rate_hz == 0 || !finite_positive(self.audio_duration_sec) {
            bail!("sample rate and duration must be positive");
        }
        if !finite_nonnegative(self.total_ms) {
            bail!("total_ms must be finite and non-negative");
        }
        for (name, value) in [
            ("cer", self.cer),
            ("wer", self.wer),
            ("audio_decode_ms", self.audio_decode_ms),
            ("resample_ms", self.resample_ms),
            ("inference_ms", self.inference_ms),
            ("decoder_ms", self.decoder_ms),
            ("postprocess_ms", self.postprocess_ms),
            ("rtf", self.rtf),
            ("peak_ram_mb", self.peak_ram_mb),
            ("peak_device_memory_mb", self.peak_device_memory_mb),
        ] {
            if value.is_some_and(|v| !finite_nonnegative(v)) {
                bail!("{name} must be finite and non-negative when present");
            }
        }
        match self.status.as_str() {
            "success" => {
                if self.cer.is_none() || self.wer.is_none() {
                    bail!("successful sample must carry CER and WER");
                }
                if self.error_code.is_some() || self.error_stage.is_some() || self.error_message.is_some() {
                    bail!("successful sample must not carry error fields");
                }
            }
            "failed" => {
                if self.cer.is_some() || self.wer.is_some() {
                    bail!("failed sample must not encode CER/WER sentinel values");
                }
                if self.error_code.as_deref().is_none_or(str::is_empty) {
                    bail!("failed sample must carry error_code");
                }
            }
            other => bail!("unsupported sample status {other}"),
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CapsuleMetric {
    pub name: String,
    pub value: f64,
    pub unit: Option<String>,
}

impl CapsuleMetric {
    pub fn validate(&self) -> Result<()> {
        if self.name.trim().is_empty() || self.name != self.name.trim() {
            bail!("metric name must be non-empty and trimmed");
        }
        if !self.value.is_finite() {
            bail!("metric {} must be finite", self.name);
        }
        if self.unit.as_deref().is_some_and(|unit| unit.trim().is_empty() || unit != unit.trim()) {
            bail!("metric unit must be non-empty and trimmed when present");
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ExperimentCapsule {
    pub manifest: CapsuleManifest,
    pub samples: Vec<CapsuleSample>,
    pub metrics: Vec<CapsuleMetric>,
}

impl ExperimentCapsule {
    pub fn validate(&self) -> Result<()> {
        self.manifest.validate()?;
        if self.samples.is_empty() {
            bail!("capsule must contain at least one sample");
        }
        for sample in &self.samples { sample.validate()?; }
        for metric in &self.metrics { metric.validate()?; }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CapsuleReceipt {
    pub schema_version: String,
    pub run_id: String,
    pub sha256: String,
    pub size_bytes: u64,
    pub sample_count: usize,
    pub metric_count: usize,
}

fn finite_positive(value: f64) -> bool { value.is_finite() && value > 0.0 }
fn finite_nonnegative(value: f64) -> bool { value.is_finite() && value >= 0.0 }
