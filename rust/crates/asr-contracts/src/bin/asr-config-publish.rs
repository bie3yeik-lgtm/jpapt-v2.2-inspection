use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use asr_contracts::{ContractError, Result};
use chrono::{SecondsFormat, Utc};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

#[path = "../revisions.rs"]
mod revisions;

use revisions::{RevisionExpectations, validate_revision_bundle};

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-config-publish: {error}");
        std::process::exit(2);
    }
}

fn run() -> std::result::Result<(), String> {
    let mut args = env::args().skip(1);
    match args.next().as_deref() {
        Some("prepare") => prepare_command(args),
        Some("write-current") => write_current_command(args),
        _ => Err(usage().to_owned()),
    }
}

fn usage() -> &'static str {
    "usage:\n  asr-config-publish prepare --source <dir> --staging <dir> --profile-set <id> [--repository-root <repo>]\n  asr-config-publish write-current --output <current.json> --config-version <config-NNNNNN> --bundle-sha256 <sha256>"
}

fn prepare_command(mut args: impl Iterator<Item = String>) -> std::result::Result<(), String> {
    let mut source = None;
    let mut staging = None;
    let mut profile_set = None;
    let mut repository_root = PathBuf::from(".");
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--source" => source = Some(PathBuf::from(take_value(&mut args, "--source")?)),
            "--staging" => staging = Some(PathBuf::from(take_value(&mut args, "--staging")?)),
            "--profile-set" => profile_set = Some(take_value(&mut args, "--profile-set")?),
            "--repository-root" => {
                repository_root = PathBuf::from(take_value(&mut args, "--repository-root")?)
            }
            other => return Err(format!("unsupported argument: {other}\n{}", usage())),
        }
    }
    let source = source.ok_or_else(|| "--source is required".to_owned())?;
    let staging = staging.ok_or_else(|| "--staging is required".to_owned())?;
    let profile_set = profile_set.ok_or_else(|| "--profile-set is required".to_owned())?;
    let summary = prepare_bundle(&repository_root, &source, &staging, &profile_set)
        .map_err(|error| error.to_string())?;
    println!("source_path={}", summary.source.display());
    println!("staging_path={}", summary.staging.display());
    println!("profile_set={}", summary.profile_set);
    println!("bundle_sha256={}", summary.bundle_sha256);
    Ok(())
}

fn write_current_command(
    mut args: impl Iterator<Item = String>,
) -> std::result::Result<(), String> {
    let mut output = None;
    let mut config_version = None;
    let mut bundle_sha256 = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--output" => output = Some(PathBuf::from(take_value(&mut args, "--output")?)),
            "--config-version" => config_version = Some(take_value(&mut args, "--config-version")?),
            "--bundle-sha256" => bundle_sha256 = Some(take_value(&mut args, "--bundle-sha256")?),
            other => return Err(format!("unsupported argument: {other}\n{}", usage())),
        }
    }
    let output = output.ok_or_else(|| "--output is required".to_owned())?;
    let config_version = config_version.ok_or_else(|| "--config-version is required".to_owned())?;
    let bundle_sha256 = bundle_sha256.ok_or_else(|| "--bundle-sha256 is required".to_owned())?;
    write_current_pointer(&output, &config_version, &bundle_sha256)
        .map_err(|error| error.to_string())?;
    println!("current_path={}", output.display());
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PrepareSummary {
    source: PathBuf,
    staging: PathBuf,
    profile_set: String,
    bundle_sha256: String,
}

fn prepare_bundle(
    repository_root: &Path,
    source: &Path,
    staging: &Path,
    profile_set: &str,
) -> Result<PrepareSummary> {
    let repository_root = repository_root.canonicalize().map_err(|source| ContractError::Io {
        path: repository_root.to_path_buf(),
        source,
    })?;
    let source = source.canonicalize().map_err(|source_error| ContractError::Io {
        path: source.to_path_buf(),
        source: source_error,
    })?;
    if !source.is_dir() {
        return Err(ContractError::validation(format!(
            "config source is not a directory: {}",
            source.display()
        )));
    }
    require_nonempty("profile set", profile_set)?;

    let catalog_path = repository_root.join("config/asr-catalog.json");
    let catalog = read_json(&catalog_path)?;
    let catalog_object = catalog.as_object().ok_or_else(|| {
        ContractError::validation("config/asr-catalog.json root must be an object")
    })?;
    if catalog_object.get("schema_version").and_then(Value::as_u64) != Some(1) {
        return Err(ContractError::validation(
            "config/asr-catalog.json schema_version must equal 1",
        ));
    }
    let catalog_id = catalog_object
        .get("catalog_id")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| ContractError::validation("config/asr-catalog.json catalog_id is required"))?;
    let profile_sets = catalog_object
        .get("profile_sets")
        .and_then(Value::as_object)
        .ok_or_else(|| ContractError::validation("config/asr-catalog.json profile_sets must be an object"))?;
    if !profile_sets.contains_key(profile_set) {
        return Err(ContractError::validation(format!(
            "unknown profile set {profile_set:?}"
        )));
    }
    let catalog_sha256 = canonical_sha256(&catalog)?;

    fs::create_dir_all(staging).map_err(|source| ContractError::Io {
        path: staging.to_path_buf(),
        source,
    })?;
    for filename in ["reference.json", "evaluation-schema.json", "datasets-lock.json"] {
        let source_path = source.join(filename);
        if !source_path.is_file() {
            return Err(ContractError::validation(format!(
                "missing required config document: {}",
                source_path.display()
            )));
        }
        let destination = staging.join(filename);
        fs::copy(&source_path, &destination).map_err(|source| ContractError::Io {
            path: destination,
            source,
        })?;
    }

    let runtime = json!({
        "schema_version": 1,
        "catalog": {
            "id": catalog_id,
            "sha256": catalog_sha256,
        },
        "profile_set": profile_set,
    });
    write_json(&staging.join("runtime.json"), &runtime)?;

    let resolved = staging.parent().unwrap_or(staging).join("resolved.json");
    if resolved.exists() {
        return Err(ContractError::validation(format!(
            "refusing to overwrite existing validation pointer: {}",
            resolved.display()
        )));
    }
    write_json(
        &resolved,
        &json!({
            "schema_version": 1,
            "config_version": "config-000000",
            "current_version": "config-000000",
            "selection_source": "current",
        }),
    )?;
    let validation = validate_revision_bundle(
        staging,
        &RevisionExpectations {
            profile_set: Some(profile_set.to_owned()),
            ..RevisionExpectations::empty()
        },
    );
    let cleanup = fs::remove_file(&resolved).map_err(|source| ContractError::Io {
        path: resolved.clone(),
        source,
    });
    let (snapshot, _) = validation?;
    cleanup?;

    Ok(PrepareSummary {
        source,
        staging: staging.to_path_buf(),
        profile_set: profile_set.to_owned(),
        bundle_sha256: snapshot.bundle_sha256,
    })
}

fn write_current_pointer(path: &Path, config_version: &str, bundle_sha256: &str) -> Result<()> {
    validate_config_version(config_version)?;
    validate_sha256("bundle SHA-256", bundle_sha256)?;
    let payload = json!({
        "schema_version": 1,
        "config_version": config_version,
        "bundle_sha256": bundle_sha256.to_ascii_lowercase(),
        "updated_at": Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true),
    });
    write_json(path, &payload)
}

fn write_json(path: &Path, value: &Value) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|source| ContractError::Io {
            path: parent.to_path_buf(),
            source,
        })?;
    }
    let mut bytes = serde_json::to_vec_pretty(value)
        .map_err(|error| ContractError::validation(format!("failed to encode JSON: {error}")))?;
    bytes.push(b'\n');
    fs::write(path, bytes).map_err(|source| ContractError::Io {
        path: path.to_path_buf(),
        source,
    })
}

fn read_json(path: &Path) -> Result<Value> {
    let text = fs::read_to_string(path).map_err(|source| ContractError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    serde_json::from_str(&text).map_err(|source| ContractError::Json {
        path: path.to_path_buf(),
        source,
    })
}

fn canonical_sha256(value: &Value) -> Result<String> {
    let bytes = serde_json::to_vec(value)
        .map_err(|error| ContractError::validation(format!("failed to canonicalize JSON: {error}")))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn validate_config_version(value: &str) -> Result<()> {
    if value.len() == 13
        && value.starts_with("config-")
        && value[7..].bytes().all(|byte| byte.is_ascii_digit())
    {
        Ok(())
    } else {
        Err(ContractError::validation(format!(
            "config version must match config-NNNNNN; got {value:?}"
        )))
    }
}

fn validate_sha256(name: &str, value: &str) -> Result<()> {
    if value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        Ok(())
    } else {
        Err(ContractError::validation(format!(
            "{name} must be a 64-character SHA-256"
        )))
    }
}

fn require_nonempty(name: &str, value: &str) -> Result<()> {
    if value.trim().is_empty() {
        Err(ContractError::validation(format!(
            "{name} must be a non-empty string"
        )))
    } else {
        Ok(())
    }
}

fn take_value(
    args: &mut impl Iterator<Item = String>,
    option: &str,
) -> std::result::Result<String, String> {
    args.next()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{option} requires a non-empty value"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_version_is_strict() {
        assert!(validate_config_version("config-000001").is_ok());
        assert!(validate_config_version("config-1").is_err());
    }

    #[test]
    fn sha256_is_strict() {
        assert!(validate_sha256("sha", &"a".repeat(64)).is_ok());
        assert!(validate_sha256("sha", "abc").is_err());
    }
}
