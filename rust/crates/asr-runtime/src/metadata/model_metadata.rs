use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::error::{Result, RuntimeError};

const GENERATED_CONTRACT_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum InputKind {
    CanonicalWaveform,
    Features,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DecoderKind {
    Ctc,
    Tdt,
    WhisperAutoregressive,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneratedCatalog {
    pub id: String,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneratedArtifact {
    pub path: String,
    pub sha256: String,
    pub size_bytes: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneratedTokenizer {
    pub kind: String,
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneratedRuntimeContract {
    pub decoder: DecoderKind,
    pub input_kind: InputKind,
    pub io: serde_json::Value,
    pub decoder_config: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneratedCandidateContract {
    pub schema_version: u32,
    pub candidate_root: PathBuf,
    pub candidate_id: String,
    pub profile_set: String,
    pub variant: String,
    pub profile: String,
    pub decoder: DecoderKind,
    pub artifact_contract: String,
    pub catalog: GeneratedCatalog,
    pub bundle_sha256: String,
    pub artifacts: BTreeMap<String, GeneratedArtifact>,
    pub tokenizer: Option<GeneratedTokenizer>,
    #[serde(default)]
    pub features: BTreeMap<String, bool>,
    pub runtime_contract: GeneratedRuntimeContract,
}

#[derive(Debug, Clone)]
pub struct CtcRuntimeContract {
    pub primary_input: String,
    pub length_input: Option<String>,
    pub logits_output: String,
    pub blank_id: i64,
}

impl GeneratedCandidateContract {
    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref();
        if !path.is_file() {
            return Err(RuntimeError::MetadataMissing(path.to_path_buf()));
        }
        let text = fs::read_to_string(path).map_err(|error| {
            RuntimeError::InvalidMetadata(format!("{}: {error}", path.display()))
        })?;
        let value: Self = serde_json::from_str(&text)
            .map_err(|error| RuntimeError::InvalidMetadata(error.to_string()))?;
        value.validate()?;
        Ok(value)
    }

    pub fn validate(&self) -> Result<()> {
        if self.schema_version != GENERATED_CONTRACT_SCHEMA_VERSION {
            return Err(RuntimeError::InvalidMetadata(format!(
                "generated candidate contract schema_version must equal {GENERATED_CONTRACT_SCHEMA_VERSION}; got {}",
                self.schema_version
            )));
        }
        for (name, value) in [
            ("candidate_id", self.candidate_id.as_str()),
            ("profile_set", self.profile_set.as_str()),
            ("variant", self.variant.as_str()),
            ("profile", self.profile.as_str()),
            ("artifact_contract", self.artifact_contract.as_str()),
            ("catalog.id", self.catalog.id.as_str()),
        ] {
            if value.trim().is_empty() {
                return Err(RuntimeError::InvalidMetadata(format!(
                    "generated candidate contract {name} must be non-empty"
                )));
            }
        }
        validate_sha256("catalog.sha256", &self.catalog.sha256)?;
        validate_sha256("bundle_sha256", &self.bundle_sha256)?;
        if self.decoder != self.runtime_contract.decoder {
            return Err(RuntimeError::InvalidMetadata(
                "candidate decoder and generated runtime contract decoder disagree".into(),
            ));
        }
        if self.artifacts.is_empty() {
            return Err(RuntimeError::InvalidMetadata(
                "generated candidate contract contains no artifacts".into(),
            ));
        }
        self.verify_artifacts()?;
        self.verify_bundle_sha256()?;
        Ok(())
    }

    pub fn artifact_path(&self, role: &str) -> Result<PathBuf> {
        let artifact = self.artifacts.get(role).ok_or_else(|| {
            RuntimeError::InvalidMetadata(format!(
                "generated candidate contract has no artifact role {role:?}"
            ))
        })?;
        self.resolve_relative(&artifact.path)
    }

    pub fn tokenizer_path(&self) -> Result<PathBuf> {
        let tokenizer = self.tokenizer.as_ref().ok_or_else(|| {
            RuntimeError::InvalidMetadata(
                "generated candidate contract has no tokenizer".into(),
            )
        })?;
        if tokenizer.kind != "vocabulary" {
            return Err(RuntimeError::UnsupportedContract(format!(
                "Rust CTC evaluator requires vocabulary tokenizer, got {:?}",
                tokenizer.kind
            )));
        }
        self.resolve_relative(&tokenizer.path)
    }

    pub fn ctc_runtime_contract(&self) -> Result<CtcRuntimeContract> {
        if self.decoder != DecoderKind::Ctc {
            return Err(RuntimeError::UnsupportedContract(format!(
                "Rust evaluator currently supports CTC only, got {:?}",
                self.decoder
            )));
        }
        if self.runtime_contract.input_kind != InputKind::CanonicalWaveform {
            return Err(RuntimeError::UnsupportedContract(
                "Rust CTC runtime requires canonical_waveform input".into(),
            ));
        }

        let primary = self
            .runtime_contract
            .io
            .get("primary")
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| {
                RuntimeError::InvalidMetadata(
                    "generated CTC runtime contract io.primary must be an object".into(),
                )
            })?;
        let primary_input = required_json_string(primary.get("input"), "io.primary.input")?;
        let logits_output = required_json_string(
            primary.get("logits_output"),
            "io.primary.logits_output",
        )?;
        let length_input = match primary.get("length_input") {
            Some(value) => Some(required_json_string(Some(value), "io.primary.length_input")?),
            None => None,
        };
        let blank_id = self
            .runtime_contract
            .decoder_config
            .get("blank_id")
            .and_then(serde_json::Value::as_i64)
            .ok_or_else(|| {
                RuntimeError::InvalidMetadata(
                    "generated CTC runtime contract decoder_config.blank_id must be an integer"
                        .into(),
                )
            })?;
        if blank_id < 0 {
            return Err(RuntimeError::InvalidMetadata(
                "generated CTC blank_id must be non-negative".into(),
            ));
        }
        Ok(CtcRuntimeContract {
            primary_input,
            length_input,
            logits_output,
            blank_id,
        })
    }

    fn verify_artifacts(&self) -> Result<()> {
        for (role, artifact) in &self.artifacts {
            validate_sha256(&format!("artifacts.{role}.sha256"), &artifact.sha256)?;
            let path = self.resolve_relative(&artifact.path)?;
            let metadata = fs::metadata(&path).map_err(|error| {
                RuntimeError::InvalidMetadata(format!("{}: {error}", path.display()))
            })?;
            if metadata.len() != artifact.size_bytes {
                return Err(RuntimeError::InvalidMetadata(format!(
                    "artifact {role:?} size mismatch: expected={}, actual={}",
                    artifact.size_bytes,
                    metadata.len()
                )));
            }
            let actual = sha256_file(&path)?;
            if !actual.eq_ignore_ascii_case(&artifact.sha256) {
                return Err(RuntimeError::InvalidMetadata(format!(
                    "artifact {role:?} SHA-256 mismatch: expected={}, actual={actual}",
                    artifact.sha256
                )));
            }
        }
        if let Some(tokenizer) = &self.tokenizer {
            let path = self.resolve_relative(&tokenizer.path)?;
            if !path.exists() {
                return Err(RuntimeError::InvalidMetadata(format!(
                    "generated tokenizer path does not exist: {}",
                    path.display()
                )));
            }
        }
        Ok(())
    }

    fn verify_bundle_sha256(&self) -> Result<()> {
        let mut digest = Sha256::new();
        for (role, artifact) in &self.artifacts {
            digest.update(
                format!("{role}\0{}\0{}\n", artifact.path, artifact.sha256).as_bytes(),
            );
        }
        let actual = format!("{:x}", digest.finalize());
        if !actual.eq_ignore_ascii_case(&self.bundle_sha256) {
            return Err(RuntimeError::InvalidMetadata(format!(
                "candidate bundle SHA-256 mismatch: expected={}, actual={actual}",
                self.bundle_sha256
            )));
        }
        Ok(())
    }

    fn resolve_relative(&self, relative: &str) -> Result<PathBuf> {
        if relative.trim().is_empty() {
            return Err(RuntimeError::InvalidMetadata(
                "generated candidate path must be non-empty".into(),
            ));
        }
        let root = fs::canonicalize(&self.candidate_root).map_err(|error| {
            RuntimeError::InvalidMetadata(format!(
                "candidate root {} cannot be canonicalized: {error}",
                self.candidate_root.display()
            ))
        })?;
        let path = fs::canonicalize(root.join(relative)).map_err(|error| {
            RuntimeError::InvalidMetadata(format!(
                "candidate path {relative:?} cannot be canonicalized: {error}"
            ))
        })?;
        if !path.starts_with(&root) {
            return Err(RuntimeError::InvalidMetadata(format!(
                "generated candidate path escapes candidate root: {relative:?}"
            )));
        }
        Ok(path)
    }
}

fn required_json_string(value: Option<&serde_json::Value>, name: &str) -> Result<String> {
    value
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .ok_or_else(|| {
            RuntimeError::InvalidMetadata(format!(
                "generated candidate contract {name} must be a non-empty string"
            ))
        })
}

fn validate_sha256(name: &str, value: &str) -> Result<()> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(RuntimeError::InvalidMetadata(format!(
            "generated candidate contract {name} must be a 64-character SHA-256"
        )));
    }
    Ok(())
}

fn sha256_file(path: &Path) -> Result<String> {
    let mut file = fs::File::open(path).map_err(|error| {
        RuntimeError::InvalidMetadata(format!("{}: {error}", path.display()))
    })?;
    let mut digest = Sha256::new();
    std::io::copy(&mut file, &mut digest).map_err(|error| {
        RuntimeError::InvalidMetadata(format!("{}: {error}", path.display()))
    })?;
    Ok(format!("{:x}", digest.finalize()))
}
