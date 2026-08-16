use std::{fs, path::Path};

use asr_runtime::ProviderKind;
use chrono::Utc;
use sha2::{Digest, Sha256};

use crate::{
    config::{detect_environment, logical_path, RevisionBundleData},
    Result,
};

pub fn sha256_file(path: &Path) -> Result<String> {
    let mut file = fs::File::open(path)?;
    let mut hasher = Sha256::new();
    std::io::copy(&mut file, &mut hasher)?;
    Ok(format!("{:x}", hasher.finalize()))
}

fn revision_context(revisions: &RevisionBundleData) -> serde_json::Value {
    let reference = &revisions.reference;
    let evaluation = &revisions.evaluation_schema;
    let datasets = &revisions.datasets_lock;
    let entries = datasets
        .get("datasets")
        .cloned()
        .unwrap_or_else(|| serde_json::json!([]));

    let runtime = revisions.runtime.as_ref().map(|value| {
        serde_json::json!({
            "document_sha256": revisions.runtime_hash,
            "catalog": value.get("catalog").cloned().unwrap_or(serde_json::Value::Null),
            "profile_set": value.get("profile_set").cloned().unwrap_or(serde_json::Value::Null)
        })
    });

    serde_json::json!({
        "config_version": revisions.config_version,
        "bundle_sha256": revisions.bundle_hash,
        "runtime": runtime,
        "reference": {
            "document_sha256": revisions.reference_hash,
            "development_artifact": reference.get("development_artifact").cloned().unwrap_or(serde_json::Value::Null),
            "upstream": reference.get("upstream").cloned().unwrap_or(serde_json::Value::Null),
            "tokenizer": reference.get("tokenizer").cloned().unwrap_or(serde_json::Value::Null),
            "reference_id": reference.pointer("/reference/id").cloned().unwrap_or(serde_json::Value::Null),
            "reference_revision": reference.pointer("/reference/revision").cloned().unwrap_or(serde_json::Value::Null),
            "canonical_framework": reference.pointer("/reference/canonical_framework").cloned().unwrap_or(serde_json::Value::Null)
        },
        "evaluation_schema": {
            "document_sha256": revisions.evaluation_schema_hash,
            "schema_id": evaluation.pointer("/schema/id").cloned().unwrap_or(serde_json::Value::Null),
            "schema_revision": evaluation.pointer("/schema/revision").cloned().unwrap_or(serde_json::Value::Null)
        },
        "datasets": {
            "document_sha256": revisions.datasets_lock_hash,
            "entries": entries
        }
    })
}

fn run_metadata(experiment_id: Option<&str>) -> serde_json::Value {
    let mut metadata = serde_json::Map::new();
    if let Some(id) = experiment_id {
        metadata.insert(
            "experiment_id".into(),
            serde_json::Value::String(id.to_owned()),
        );
    }
    for (key, env_name) in [
        ("hf_target_id", "HF_TARGET_ID"),
        ("hf_bucket", "HF_BUCKET"),
        ("hf_model_repo", "HF_MODEL_REPO"),
        ("runtime_variant", "ASR_RUNTIME_VARIANT"),
        ("runtime_profile", "EXPECTED_RUNTIME_PROFILE"),
    ] {
        if let Ok(value) = std::env::var(env_name) {
            if !value.is_empty() {
                metadata.insert(key.into(), serde_json::Value::String(value));
            }
        }
    }
    serde_json::Value::Object(metadata)
}

pub fn build_run_context(
    model: &Path,
    model_id: &str,
    candidate_id: Option<&str>,
    experiment_id: Option<&str>,
    provider: ProviderKind,
    evaluation: &str,
    revisions: &RevisionBundleData,
) -> Result<serde_json::Value> {
    let sha = sha256_file(model)?;
    let size = fs::metadata(model)?.len();
    let now = Utc::now();
    let safe_model_id = model_id.replace('/', "-").replace('_', "-");
    let run_id = format!(
        "{}-{}-{}-{}-{}",
        now.format("%Y%m%dT%H%M%SZ"),
        safe_model_id,
        detect_environment(),
        provider,
        &sha[..8]
    );

    Ok(serde_json::json!({
        "schema_version": 2,
        "run_id": run_id,
        "created_at": now.to_rfc3339(),
        "config_identity": format!("{model_id}:{}:{provider}:{evaluation}", detect_environment()),
        "model_id": model_id,
        "environment_id": detect_environment(),
        "provider_id": provider.to_string(),
        "evaluation_id": evaluation,
        "artifact": {
            "path": logical_path(model),
            "sha256": sha,
            "size_bytes": size,
            "candidate_id": candidate_id,
            "artifact_role": "primary"
        },
        "git": {
            "repository": std::env::var("GITHUB_REPOSITORY").ok(),
            "commit": std::env::var("GITHUB_SHA").ok(),
            "ref": std::env::var("GITHUB_REF").ok(),
            "dirty": null
        },
        "host": {
            "os": std::env::consts::OS,
            "architecture": std::env::consts::ARCH,
            "hostname": null,
            "python_version": "n/a",
            "implementation": "rust",
            "is_wsl": false,
            "github_runner_os": std::env::var("RUNNER_OS").ok(),
            "github_runner_arch": std::env::var("RUNNER_ARCH").ok(),
            "github_run_id": std::env::var("GITHUB_RUN_ID").ok(),
            "github_run_attempt": std::env::var("GITHUB_RUN_ATTEMPT").ok()
        },
        "runtime": {
            "implementation": "rust",
            "backend": "onnxruntime",
            "backend_version": null,
            "provider_id": provider.to_string(),
            "provider_ort_name": provider.ort_name(),
            "provider_available": true
        },
        "revisions": revision_context(revisions),
        "config": {
            "identity": format!("{model_id}:{}:{provider}:{evaluation}", detect_environment()),
            "sources": {
                "model": format!("config/models/{model_id}.toml"),
                "provider": format!("config/providers/{provider}.toml"),
                "environment": format!("config/environments/{}.toml",detect_environment()),
                "evaluation": format!("config/evaluation/{evaluation}.toml")
            },
            "resolved": {
                "model": {}, "provider": {}, "environment": {}, "evaluation": {},
                "resolved": {
                    "model_id": model_id,
                    "provider_id": provider.to_string(),
                    "environment_id": detect_environment(),
                    "evaluation_id": evaluation
                }
            }
        },
        "metadata": run_metadata(experiment_id)
    }))
}
