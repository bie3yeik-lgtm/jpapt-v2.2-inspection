use std::{
    fs,
    path::{Path, PathBuf},
};

use sha2::{Digest, Sha256};

use crate::{EvalError, Result};

#[derive(Debug, Clone)]
pub struct RevisionBundleData {
    pub reference_hash: String,
    pub evaluation_schema_hash: String,
    pub datasets_lock_hash: String,
    pub runtime_hash: String,
    pub bundle_hash: String,
    pub config_version: Option<String>,
    pub reference: serde_json::Value,
    pub evaluation_schema: serde_json::Value,
    pub datasets_lock: serde_json::Value,
    pub runtime: serde_json::Value,
}

fn canonical(path: &Path) -> Result<(serde_json::Value, String)> {
    if !path.is_file() {
        return Err(EvalError::InvalidInput(format!(
            "required revision document does not exist: {}",
            path.display()
        )));
    }
    let value: serde_json::Value = serde_json::from_str(&fs::read_to_string(path)?)?;
    if value.get("schema_version").and_then(serde_json::Value::as_u64) != Some(1) {
        return Err(EvalError::InvalidInput(format!(
            "{}: schema_version must equal 1",
            path.display()
        )));
    }
    let bytes = serde_json::to_vec(&value)?;
    Ok((value, format!("{:x}", Sha256::digest(bytes))))
}

pub fn load_revision_bundle(root: impl AsRef<Path>) -> Result<RevisionBundleData> {
    let root = root.as_ref();
    let (reference, reference_hash) = canonical(&root.join("reference.json"))?;
    let (evaluation_schema, evaluation_schema_hash) =
        canonical(&root.join("evaluation-schema.json"))?;
    let (datasets_lock, datasets_lock_hash) = canonical(&root.join("datasets-lock.json"))?;
    let (runtime, runtime_hash) = canonical(&root.join("runtime.json"))?;

    for (name, value) in [
        ("reference.json", &reference),
        ("evaluation-schema.json", &evaluation_schema),
    ] {
        if value.get("decoder").is_some()
            || value.get("decoders").is_some()
            || value.get("decorders").is_some()
        {
            return Err(EvalError::InvalidInput(format!(
                "{name} must not repeat decoder declarations"
            )));
        }
    }

    let catalog = runtime
        .get("catalog")
        .and_then(serde_json::Value::as_object)
        .ok_or_else(|| EvalError::InvalidInput("runtime.json catalog must be an object".into()))?;
    for key in ["id", "sha256"] {
        if !catalog
            .get(key)
            .and_then(serde_json::Value::as_str)
            .is_some_and(|value| !value.is_empty())
        {
            return Err(EvalError::InvalidInput(format!(
                "runtime.json catalog.{key} must be a non-empty string"
            )));
        }
    }
    if !runtime
        .get("profile_set")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.is_empty())
    {
        return Err(EvalError::InvalidInput(
            "runtime.json profile_set must be a non-empty string".into(),
        ));
    }

    let mut digest = Sha256::new();
    for hash in [
        &reference_hash,
        &evaluation_schema_hash,
        &datasets_lock_hash,
        &runtime_hash,
    ] {
        digest.update(hash.as_bytes());
    }
    let bundle_hash = format!("{:x}", digest.finalize());

    let resolved = root.parent().unwrap_or(root).join("resolved.json");
    let config_version = if resolved.is_file() {
        let value: serde_json::Value = serde_json::from_str(&fs::read_to_string(&resolved)?)?;
        if value.get("schema_version").and_then(serde_json::Value::as_u64) != Some(1) {
            return Err(EvalError::InvalidInput(format!(
                "{}: schema_version must equal 1",
                resolved.display()
            )));
        }
        value
            .get("config_version")
            .and_then(serde_json::Value::as_str)
            .map(ToOwned::to_owned)
    } else {
        None
    };

    Ok(RevisionBundleData {
        reference_hash,
        evaluation_schema_hash,
        datasets_lock_hash,
        runtime_hash,
        bundle_hash,
        config_version,
        reference,
        evaluation_schema,
        datasets_lock,
        runtime,
    })
}

pub fn detect_environment() -> &'static str {
    if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        "macos"
    } else {
        "linux"
    }
}

pub fn logical_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

pub fn require_file(path: impl AsRef<Path>) -> Result<PathBuf> {
    let path = path.as_ref().to_path_buf();
    if !path.is_file() {
        return Err(EvalError::InvalidInput(format!(
            "file does not exist: {}",
            path.display()
        )));
    }
    Ok(path)
}
