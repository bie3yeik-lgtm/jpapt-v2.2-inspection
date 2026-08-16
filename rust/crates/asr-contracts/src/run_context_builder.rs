use std::env;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::Command;

use chrono::{SecondsFormat, Utc};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::project_config::{apply_runtime_overrides, resolve_project_config};
use crate::revisions::{RevisionExpectations, validate_revision_bundle};
use crate::{ContractError, Result, validate_run_context};

#[derive(Debug, Clone)]
pub struct RunContextBuildOptions {
    pub repository_root: PathBuf,
    pub model_id: String,
    pub provider_id: String,
    pub evaluation_id: String,
    pub environment_id: String,
    pub revisions_root: PathBuf,
    pub candidate_contract: PathBuf,
    pub strict_provider: bool,
    pub optimization_level: String,
    pub experiment_id: Option<String>,
}

pub fn build_run_context(options: &RunContextBuildOptions) -> Result<Value> {
    let repository_root = options
        .repository_root
        .canonicalize()
        .map_err(|source| ContractError::Io {
            path: options.repository_root.clone(),
            source,
        })?;

    let mut config = resolve_project_config(
        &repository_root,
        &options.model_id,
        &options.provider_id,
        &options.evaluation_id,
        &options.environment_id,
    )?;
    apply_runtime_overrides(
        &mut config,
        options.strict_provider,
        &options.optimization_level,
    )?;

    let candidate = read_json(&options.candidate_contract)?;
    reject_nulls(&candidate, "$.metadata.candidate")?;
    let candidate_id = required_string(&candidate, "/candidate_id", "candidate_id")?;
    let profile_set = required_string(&candidate, "/profile_set", "profile_set")?;
    let variant = required_string(&candidate, "/variant", "variant")?;
    let profile = required_string(&candidate, "/profile", "profile")?;
    let decoder = required_string(&candidate, "/decoder", "decoder")?;
    let catalog_id = required_string(&candidate, "/catalog/id", "catalog.id")?;
    let catalog_sha256 = required_string(&candidate, "/catalog/sha256", "catalog.sha256")?;
    validate_sha256("catalog.sha256", catalog_sha256)?;

    let mut expectations = RevisionExpectations::empty();
    expectations.profile_set = Some(profile_set.to_owned());
    expectations.runtime_variant = Some(variant.to_owned());
    expectations.runtime_profile = Some(profile.to_owned());
    expectations.decoder = Some(decoder.to_owned());
    let (revisions, resolution) = validate_revision_bundle(&options.revisions_root, &expectations)?;

    if resolution.variant != variant || resolution.profile != profile || resolution.decoder != decoder {
        return Err(ContractError::validation(
            "candidate runtime identity does not match resolved revision runtime identity",
        ));
    }
    if revisions.runtime.catalog.id != catalog_id || revisions.runtime.catalog.sha256 != catalog_sha256 {
        return Err(ContractError::validation(
            "candidate catalog does not match revision runtime catalog",
        ));
    }

    let (artifact_role, artifact_value) = primary_artifact(&candidate)?;
    let artifact_path = required_string(artifact_value, "/path", "artifact.path")?;
    let artifact_sha256 = required_string(artifact_value, "/sha256", "artifact.sha256")?;
    let artifact_size = required_u64(artifact_value, "/size_bytes", "artifact.size_bytes")?;
    if artifact_size == 0 {
        return Err(ContractError::validation("artifact.size_bytes must be positive"));
    }
    validate_sha256("artifact.sha256", artifact_sha256)?;

    let candidate_root = PathBuf::from(required_string(
        &candidate,
        "/candidate_root",
        "candidate_root",
    )?);
    let candidate_root = candidate_root
        .canonicalize()
        .map_err(|source| ContractError::Io {
            path: candidate_root.clone(),
            source,
        })?;
    let artifact_file = canonical_under_root(&candidate_root, Path::new(artifact_path))?;
    verify_file(&artifact_file, artifact_size, artifact_sha256)?;

    let created = Utc::now();
    let run_id = make_run_id(
        &config.model_id,
        &config.environment_id,
        &config.provider_id,
        &config.evaluation_id,
        artifact_sha256,
        &created.format("%Y%m%dT%H%M%SZ").to_string(),
    );

    let git = git_identity(&repository_root)?;
    let host = host_identity();
    let logical_artifact = logical_path(&repository_root, &artifact_file);

    let mut metadata = serde_json::Map::new();
    metadata.insert("candidate".into(), candidate.clone());
    metadata.insert("runtime_variant".into(), Value::String(variant.to_owned()));
    metadata.insert("runtime_profile".into(), Value::String(profile.to_owned()));
    metadata.insert(
        "runtime_overrides".into(),
        json!({
            "strict_provider": options.strict_provider,
            "optimization_level": options.optimization_level,
        }),
    );
    if let Some(experiment_id) = options.experiment_id.as_deref().filter(|value| !value.is_empty()) {
        metadata.insert("experiment_id".into(), Value::String(experiment_id.to_owned()));
    }
    for (key, variable) in [
        ("hf_target_id", "HF_TARGET_ID"),
        ("hf_bucket", "HF_BUCKET"),
        ("hf_model_repo", "HF_MODEL_REPO"),
    ] {
        if let Ok(value) = env::var(variable)
            && !value.trim().is_empty()
        {
            metadata.insert(key.into(), Value::String(value));
        }
    }

    let context = json!({
        "schema_version": 2,
        "run_id": run_id,
        "created_at": created.to_rfc3339_opts(SecondsFormat::Secs, true),
        "config_identity": config.identity,
        "model_id": config.model_id,
        "environment_id": config.environment_id,
        "provider_id": config.provider_id,
        "evaluation_id": config.evaluation_id,
        "artifact": {
            "path": logical_artifact,
            "sha256": artifact_sha256,
            "size_bytes": artifact_size,
            "candidate_id": candidate_id,
            "artifact_role": artifact_role,
        },
        "git": git,
        "host": host,
        "runtime": {
            "implementation": "rust",
            "backend": "onnxruntime",
            "backend_version": "resolved-by-rust-runtime",
            "provider_id": config.provider_id,
            "provider_ort_name": config.provider_ort_name,
            "provider_available": false,
        },
        "revisions": revisions,
        "config": {
            "identity": config.identity,
            "sources": config.sources,
            "resolved": config.resolved,
        },
        "metadata": metadata,
    });
    validate_run_context(&context)?;
    Ok(context)
}

pub fn write_run_context(path: &Path, value: &Value) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|source| ContractError::Io {
            path: parent.to_path_buf(),
            source,
        })?;
    }
    let bytes = serde_json::to_vec_pretty(value)
        .map_err(|error| ContractError::validation(format!("serialize run context: {error}")))?;
    let temporary = path.with_extension("json.tmp");
    fs::write(&temporary, [bytes.as_slice(), b"\n"].concat()).map_err(|source| {
        ContractError::Io {
            path: temporary.clone(),
            source,
        }
    })?;
    fs::rename(&temporary, path).map_err(|source| ContractError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    Ok(())
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

fn primary_artifact(candidate: &Value) -> Result<(String, &Value)> {
    let artifacts = candidate
        .get("artifacts")
        .and_then(Value::as_object)
        .ok_or_else(|| ContractError::validation("candidate artifacts must be an object"))?;
    if artifacts.is_empty() {
        return Err(ContractError::validation("candidate artifacts must not be empty"));
    }
    if let Some(value) = artifacts.get("primary") {
        return Ok(("primary".into(), value));
    }
    if artifacts.len() == 1 {
        let (role, value) = artifacts.iter().next().expect("non-empty");
        return Ok((role.clone(), value));
    }
    if let Some(value) = artifacts.get("encoder") {
        return Ok(("encoder".into(), value));
    }
    Err(ContractError::validation(
        "candidate has multiple artifacts and no primary/encoder role",
    ))
}

fn canonical_under_root(root: &Path, relative: &Path) -> Result<PathBuf> {
    if relative.is_absolute() {
        return Err(ContractError::validation(
            "candidate artifact path must be relative to candidate_root",
        ));
    }
    let path = root.join(relative);
    let canonical = path.canonicalize().map_err(|source| ContractError::Io {
        path: path.clone(),
        source,
    })?;
    if !canonical.starts_with(root) {
        return Err(ContractError::validation(
            "candidate artifact escapes candidate_root",
        ));
    }
    Ok(canonical)
}

fn verify_file(path: &Path, expected_size: u64, expected_sha256: &str) -> Result<()> {
    let metadata = fs::metadata(path).map_err(|source| ContractError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    if !metadata.is_file() || metadata.len() != expected_size {
        return Err(ContractError::validation(format!(
            "candidate artifact size mismatch for {}: expected={expected_size}, actual={}",
            path.display(),
            metadata.len()
        )));
    }
    let mut file = fs::File::open(path).map_err(|source| ContractError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|source| ContractError::Io {
            path: path.to_path_buf(),
            source,
        })?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    let actual = format!("{:x}", digest.finalize());
    if !actual.eq_ignore_ascii_case(expected_sha256) {
        return Err(ContractError::validation(format!(
            "candidate artifact SHA-256 mismatch for {}: expected={expected_sha256}, actual={actual}",
            path.display()
        )));
    }
    Ok(())
}

fn git_identity(repository_root: &Path) -> Result<Value> {
    let commit = env::var("GITHUB_SHA")
        .ok()
        .filter(|value| !value.is_empty())
        .unwrap_or(git_output(repository_root, &["rev-parse", "HEAD"], false)?);
    let git_ref = env::var("GITHUB_REF")
        .ok()
        .filter(|value| !value.is_empty())
        .unwrap_or(git_output(
            repository_root,
            &["rev-parse", "--abbrev-ref", "HEAD"],
            false,
        )?);
    let repository = env::var("GITHUB_REPOSITORY")
        .ok()
        .filter(|value| !value.is_empty())
        .unwrap_or(git_output(
            repository_root,
            &["config", "--get", "remote.origin.url"],
            false,
        )?);
    let dirty = !git_output(
        repository_root,
        &["status", "--porcelain", "--untracked-files=no"],
        true,
    )?
    .is_empty();
    Ok(json!({
        "repository": repository,
        "commit": commit,
        "ref": git_ref,
        "dirty": dirty,
    }))
}

fn git_output(repository_root: &Path, args: &[&str], allow_empty: bool) -> Result<String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(repository_root)
        .args(args)
        .output()
        .map_err(|error| ContractError::validation(format!("unable to execute git: {error}")))?;
    if !output.status.success() {
        return Err(ContractError::validation(format!(
            "git {} failed with {}",
            args.join(" "),
            output.status
        )));
    }
    let value = String::from_utf8(output.stdout)
        .map_err(|error| ContractError::validation(format!("git output is not UTF-8: {error}")))?
        .trim()
        .to_owned();
    if value.is_empty() && !allow_empty {
        return Err(ContractError::validation(format!(
            "git {} returned an empty value",
            args.join(" ")
        )));
    }
    Ok(value)
}

fn host_identity() -> Value {
    let os = match env::consts::OS {
        "linux" => "Linux",
        "windows" => "Windows",
        "macos" => "Darwin",
        other => other,
    };
    let hostname = env::var("HOSTNAME")
        .or_else(|_| env::var("COMPUTERNAME"))
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "unknown-host".into());
    json!({
        "os": os,
        "architecture": env::consts::ARCH,
        "hostname": hostname,
        "python_version": "not-applicable",
        "implementation": "Rust",
        "is_wsl": is_wsl(),
        "github_runner_os": env::var("RUNNER_OS").unwrap_or_else(|_| "local".into()),
        "github_runner_arch": env::var("RUNNER_ARCH").unwrap_or_else(|_| "local".into()),
        "github_run_id": env::var("GITHUB_RUN_ID").unwrap_or_else(|_| "local".into()),
        "github_run_attempt": env::var("GITHUB_RUN_ATTEMPT").unwrap_or_else(|_| "local".into()),
    })
}

fn is_wsl() -> bool {
    env::var_os("WSL_DISTRO_NAME").is_some()
        || fs::read_to_string("/proc/version")
            .map(|value| value.to_ascii_lowercase().contains("microsoft"))
            .unwrap_or(false)
}

fn make_run_id(
    model_id: &str,
    environment_id: &str,
    provider_id: &str,
    evaluation_id: &str,
    candidate_sha256: &str,
    timestamp: &str,
) -> String {
    let safe_model = model_id.replace(['/', '_'], "-");
    let suffix = Uuid::new_v4().simple().to_string();
    format!(
        "{timestamp}-{safe_model}-{environment_id}-{provider_id}-{evaluation_id}-{}-{}",
        &candidate_sha256[..8],
        &suffix[..8]
    )
}

fn logical_path(repository_root: &Path, path: &Path) -> String {
    path.strip_prefix(repository_root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn required_string<'a>(value: &'a Value, pointer: &str, name: &str) -> Result<&'a str> {
    value
        .pointer(pointer)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| ContractError::validation(format!("{name} must be a non-empty string")))
}

fn required_u64(value: &Value, pointer: &str, name: &str) -> Result<u64> {
    value
        .pointer(pointer)
        .and_then(Value::as_u64)
        .ok_or_else(|| ContractError::validation(format!("{name} must be an integer")))
}

fn validate_sha256(name: &str, value: &str) -> Result<()> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(ContractError::validation(format!(
            "{name} must be a 64-character hexadecimal SHA-256"
        )));
    }
    Ok(())
}

fn reject_nulls(value: &Value, path: &str) -> Result<()> {
    match value {
        Value::Null => Err(ContractError::validation(format!(
            "null is forbidden at {path}"
        ))),
        Value::Array(values) => {
            for (index, value) in values.iter().enumerate() {
                reject_nulls(value, &format!("{path}[{index}]"))?;
            }
            Ok(())
        }
        Value::Object(values) => {
            for (key, value) in values {
                reject_nulls(value, &format!("{path}.{key}"))?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}
