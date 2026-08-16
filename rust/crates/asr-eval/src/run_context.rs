use std::{collections::BTreeMap, fs, path::Path};

use asr_runtime::metadata::model_metadata::GeneratedCandidateContract;
use serde::{Deserialize, Serialize};

use crate::{EvalError, Result};

pub const RUN_CONTEXT_SCHEMA_VERSION: u32 = 2;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunContextV2 {
    pub schema_version: u32,
    pub run_id: String,
    pub created_at: String,
    pub config_identity: String,
    pub model_id: String,
    pub environment_id: String,
    pub provider_id: String,
    pub evaluation_id: String,
    pub artifact: ArtifactIdentity,
    pub git: GitIdentity,
    pub host: HostIdentity,
    pub runtime: RuntimeIdentity,
    pub revisions: serde_json::Value,
    pub config: serde_json::Value,
    pub metadata: BTreeMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ArtifactIdentity {
    pub path: String,
    pub sha256: String,
    pub size_bytes: u64,
    pub candidate_id: String,
    pub artifact_role: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GitIdentity {
    pub repository: String,
    pub commit: String,
    #[serde(rename = "ref")]
    pub git_ref: String,
    pub dirty: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostIdentity {
    pub os: String,
    pub architecture: String,
    pub hostname: String,
    pub python_version: String,
    pub implementation: String,
    pub is_wsl: bool,
    pub github_runner_os: String,
    pub github_runner_arch: String,
    pub github_run_id: String,
    pub github_run_attempt: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeIdentity {
    pub implementation: String,
    pub backend: String,
    pub backend_version: String,
    pub provider_id: String,
    pub provider_ort_name: String,
    pub provider_available: bool,
}

impl RunContextV2 {
    pub fn load(path: &Path) -> Result<Self> {
        let text = fs::read_to_string(path)?;
        let value: serde_json::Value = serde_json::from_str(&text)?;
        reject_nulls(&value, "$")?;
        let context: Self = serde_json::from_value(value)?;
        context.validate()?;
        Ok(context)
    }

    pub fn validate(&self) -> Result<()> {
        if self.schema_version != RUN_CONTEXT_SCHEMA_VERSION {
            return Err(EvalError::InvalidInput(format!(
                "Rust evaluator requires run-context schema_version {RUN_CONTEXT_SCHEMA_VERSION}; got {}",
                self.schema_version
            )));
        }

        for (name, value) in [
            ("run_id", self.run_id.as_str()),
            ("created_at", self.created_at.as_str()),
            ("config_identity", self.config_identity.as_str()),
            ("model_id", self.model_id.as_str()),
            ("environment_id", self.environment_id.as_str()),
            ("provider_id", self.provider_id.as_str()),
            ("evaluation_id", self.evaluation_id.as_str()),
            ("artifact.path", self.artifact.path.as_str()),
            ("artifact.sha256", self.artifact.sha256.as_str()),
            ("artifact.candidate_id", self.artifact.candidate_id.as_str()),
            (
                "artifact.artifact_role",
                self.artifact.artifact_role.as_str(),
            ),
            ("git.repository", self.git.repository.as_str()),
            ("git.commit", self.git.commit.as_str()),
            ("git.ref", self.git.git_ref.as_str()),
            ("host.os", self.host.os.as_str()),
            ("host.architecture", self.host.architecture.as_str()),
            ("host.hostname", self.host.hostname.as_str()),
            ("host.python_version", self.host.python_version.as_str()),
            ("host.implementation", self.host.implementation.as_str()),
            ("host.github_runner_os", self.host.github_runner_os.as_str()),
            (
                "host.github_runner_arch",
                self.host.github_runner_arch.as_str(),
            ),
            ("host.github_run_id", self.host.github_run_id.as_str()),
            (
                "host.github_run_attempt",
                self.host.github_run_attempt.as_str(),
            ),
            (
                "runtime.implementation",
                self.runtime.implementation.as_str(),
            ),
            ("runtime.backend", self.runtime.backend.as_str()),
            (
                "runtime.backend_version",
                self.runtime.backend_version.as_str(),
            ),
            ("runtime.provider_id", self.runtime.provider_id.as_str()),
            (
                "runtime.provider_ort_name",
                self.runtime.provider_ort_name.as_str(),
            ),
        ] {
            require_nonempty(name, value)?;
        }

        validate_sha256("artifact.sha256", &self.artifact.sha256)?;
        validate_git_commit(&self.git.commit)?;

        if self.artifact.size_bytes == 0 {
            return Err(EvalError::InvalidInput(
                "run-context artifact.size_bytes must be greater than zero".into(),
            ));
        }
        if self.artifact.artifact_role != "primary" {
            return Err(EvalError::InvalidInput(format!(
                "Rust CTC evaluator requires artifact.artifact_role=primary; got {:?}",
                self.artifact.artifact_role
            )));
        }
        require_one_of(
            "environment_id",
            &self.environment_id,
            &["linux", "windows", "macos"],
        )?;
        require_one_of(
            "provider_id",
            &self.provider_id,
            &["cpu", "cuda", "directml", "coreml"],
        )?;
        require_one_of(
            "evaluation_id",
            &self.evaluation_id,
            &["smoke", "parity", "coreml-parity", "full"],
        )?;
        if self.runtime.implementation != "rust" {
            return Err(EvalError::InvalidInput(format!(
                "Rust evaluator requires runtime.implementation=rust; got {:?}",
                self.runtime.implementation
            )));
        }
        if self.runtime.backend != "onnxruntime" {
            return Err(EvalError::InvalidInput(format!(
                "Rust evaluator requires runtime.backend=onnxruntime; got {:?}",
                self.runtime.backend
            )));
        }
        if self.runtime.provider_id != self.provider_id {
            return Err(EvalError::InvalidInput(
                "run-context runtime.provider_id must equal provider_id".into(),
            ));
        }

        let candidate_value = self.metadata.get("candidate").ok_or_else(|| {
            EvalError::InvalidInput("run-context metadata.candidate is required".into())
        })?;
        let candidate: GeneratedCandidateContract =
            serde_json::from_value(candidate_value.clone())?;
        candidate.validate()?;
        if candidate.candidate_id != self.artifact.candidate_id {
            return Err(EvalError::InvalidInput(
                "run-context artifact.candidate_id must match metadata.candidate.candidate_id"
                    .into(),
            ));
        }
        let primary = candidate.artifacts.get("primary").ok_or_else(|| {
            EvalError::InvalidInput("run-context candidate has no primary artifact".into())
        })?;
        if primary.sha256 != self.artifact.sha256 || primary.size_bytes != self.artifact.size_bytes
        {
            return Err(EvalError::InvalidInput(
                "run-context artifact identity must match metadata.candidate primary artifact"
                    .into(),
            ));
        }
        Ok(())
    }

    pub fn into_value(self) -> Result<serde_json::Value> {
        Ok(serde_json::to_value(self)?)
    }
}

fn require_nonempty(name: &str, value: &str) -> Result<()> {
    if value.trim().is_empty() {
        return Err(EvalError::InvalidInput(format!(
            "run-context {name} must be a non-empty string"
        )));
    }
    Ok(())
}

fn require_one_of(name: &str, value: &str, allowed: &[&str]) -> Result<()> {
    if !allowed.contains(&value) {
        return Err(EvalError::InvalidInput(format!(
            "run-context {name} has unsupported value {value:?}; expected one of {}",
            allowed.join(", ")
        )));
    }
    Ok(())
}

fn validate_sha256(name: &str, value: &str) -> Result<()> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(EvalError::InvalidInput(format!(
            "run-context {name} must be a 64-character SHA-256"
        )));
    }
    Ok(())
}

fn validate_git_commit(value: &str) -> Result<()> {
    if !(7..=64).contains(&value.len()) || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(EvalError::InvalidInput(
            "run-context git.commit must be a 7-64 character hexadecimal commit identity".into(),
        ));
    }
    Ok(())
}

fn reject_nulls(value: &serde_json::Value, path: &str) -> Result<()> {
    match value {
        serde_json::Value::Null => Err(EvalError::InvalidInput(format!(
            "run-context must not contain null: {path}"
        ))),
        serde_json::Value::Array(items) => {
            for (index, item) in items.iter().enumerate() {
                reject_nulls(item, &format!("{path}[{index}]"))?;
            }
            Ok(())
        }
        serde_json::Value::Object(entries) => {
            for (key, item) in entries {
                reject_nulls(item, &format!("{path}.{key}"))?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_null_anywhere() {
        let value = serde_json::json!({"metadata": {"unknown": null}});
        let error = reject_nulls(&value, "$").expect_err("null must fail");
        assert!(error.to_string().contains("$.metadata.unknown"));
    }

    #[test]
    fn rejects_invalid_sha256() {
        let error =
            validate_sha256("artifact.sha256", "not-a-sha").expect_err("invalid sha must fail");
        assert!(error.to_string().contains("64-character SHA-256"));
    }

    #[test]
    fn rejects_unknown_provider() {
        let error = require_one_of("provider_id", "magic", &["cpu", "coreml"])
            .expect_err("unknown provider must fail");
        assert!(error.to_string().contains("unsupported value"));
    }
}
