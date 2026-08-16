use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, thiserror::Error)]
pub enum HfError {
    #[error("I/O error for {path}: {source}")]
    Io {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
    #[error("invalid JSON: {0}")]
    Json(#[from] serde_json::Error),
    #[error("HF target contract violation: {0}")]
    Contract(String),
}

pub type Result<T> = std::result::Result<T, HfError>;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ResolvedHfTarget {
    pub target_id: String,
    pub hf_bucket: String,
    pub hf_model_repo: String,
    pub expected_development_repo_id: String,
    pub expected_upstream_repo_id: String,
    pub expected_tokenizer_repo_id: String,
    pub expected_framework: String,
    pub profile_set: String,
    pub runtime_variant: String,
    pub runtime_profile: String,
    pub decoder: String,
}

impl ResolvedHfTarget {
    pub fn environment_values(&self) -> Vec<(&'static str, &str)> {
        vec![
            ("HF_BUCKET", &self.hf_bucket),
            ("HF_MODEL_REPO", &self.hf_model_repo),
            (
                "EXPECTED_DEVELOPMENT_REPO_ID",
                &self.expected_development_repo_id,
            ),
            ("EXPECTED_UPSTREAM_REPO_ID", &self.expected_upstream_repo_id),
            (
                "EXPECTED_TOKENIZER_REPO_ID",
                &self.expected_tokenizer_repo_id,
            ),
            ("EXPECTED_FRAMEWORK", &self.expected_framework),
            ("HF_PROFILE_SET", &self.profile_set),
            ("ASR_RUNTIME_VARIANT", &self.runtime_variant),
            ("EXPECTED_RUNTIME_PROFILE", &self.runtime_profile),
            ("EXPECTED_DECODER", &self.decoder),
            ("HF_TARGET_ID", &self.target_id),
        ]
    }

    pub fn output_values(&self) -> Vec<(&'static str, &str)> {
        vec![
            ("target_id", &self.target_id),
            ("hf_bucket", &self.hf_bucket),
            ("hf_model_repo", &self.hf_model_repo),
            ("profile_set", &self.profile_set),
            ("runtime_variant", &self.runtime_variant),
            ("runtime_profile", &self.runtime_profile),
            ("decoder", &self.decoder),
            ("framework", &self.expected_framework),
        ]
    }
}

#[derive(Debug, Clone)]
pub enum TargetSelector {
    Id(String),
    Bucket(String),
}

#[derive(Debug, Clone)]
pub struct ResolveTargetOptions {
    pub repository_root: PathBuf,
    pub selector: TargetSelector,
    pub runtime_variant: Option<String>,
    pub targets_json: Option<String>,
}

#[derive(Debug, Deserialize)]
struct TargetDocument {
    schema_version: u32,
    target: TargetIdentity,
    upstream: UpstreamIdentity,
    reference: ReferenceIdentity,
    runtime: RuntimeIdentity,
    storage: StorageIdentity,
    evaluation: EvaluationIdentity,
}

#[derive(Debug, Deserialize)]
struct TargetIdentity {
    id: String,
    model_id: String,
}

#[derive(Debug, Deserialize)]
struct UpstreamIdentity {
    repo_id: String,
}

#[derive(Debug, Deserialize)]
struct ReferenceIdentity {
    canonical_framework: String,
}

#[derive(Debug, Deserialize)]
struct RuntimeIdentity {
    profile_set: String,
}

#[derive(Debug, Deserialize)]
struct StorageIdentity {
    bucket: String,
    model_repo: String,
}

#[derive(Debug, Deserialize)]
struct EvaluationIdentity {
    datasets_policy: String,
}

#[derive(Debug, Deserialize)]
struct Catalog {
    schema_version: u32,
    decoder_profiles: BTreeMap<String, DecoderProfile>,
    profile_sets: BTreeMap<String, ProfileSet>,
}

#[derive(Debug, Deserialize)]
struct DecoderProfile {
    decoder: String,
}

#[derive(Debug, Deserialize)]
struct ProfileSet {
    variants: BTreeMap<String, String>,
    default_variant: String,
}

#[derive(Debug, Clone)]
struct Route {
    bucket: String,
    model_repo: String,
}

pub fn resolve_target(options: &ResolveTargetOptions) -> Result<ResolvedHfTarget> {
    let root = options
        .repository_root
        .canonicalize()
        .map_err(|source| HfError::Io {
            path: options.repository_root.clone(),
            source,
        })?;
    let routes = parse_routes(options.targets_json.as_deref())?;
    let target_id = match &options.selector {
        TargetSelector::Id(value) => require_nonempty("target id", value)?.to_owned(),
        TargetSelector::Bucket(bucket) => target_from_bucket(bucket, &routes)?,
    };
    validate_identifier(&target_id)?;

    let target_path = root
        .join("config/hf-targets")
        .join(format!("{target_id}.toml"));
    let target: TargetDocument = load_toml(&target_path)?;
    if target.schema_version != 2 {
        return Err(contract(format!(
            "{}: schema_version must equal 2",
            target_path.display()
        )));
    }
    expect_equal(
        "target filename",
        &target_id,
        "target.id",
        &target.target.id,
    )?;
    for (name, value) in [
        ("target.model_id", target.target.model_id.as_str()),
        ("upstream.repo_id", target.upstream.repo_id.as_str()),
        (
            "reference.canonical_framework",
            target.reference.canonical_framework.as_str(),
        ),
        ("runtime.profile_set", target.runtime.profile_set.as_str()),
        ("storage.bucket", target.storage.bucket.as_str()),
        ("storage.model_repo", target.storage.model_repo.as_str()),
        (
            "evaluation.datasets_policy",
            target.evaluation.datasets_policy.as_str(),
        ),
    ] {
        require_nonempty(name, value)?;
    }

    let model_path = root
        .join("config/models")
        .join(format!("{}.toml", target.target.model_id));
    let model: toml::Value = load_toml(&model_path)?;
    if model
        .get("schema_version")
        .and_then(toml::Value::as_integer)
        != Some(1)
    {
        return Err(contract(format!(
            "{}: schema_version must equal 1",
            model_path.display()
        )));
    }
    let model_id = toml_string(&model, &["model", "id"], "model.id")?;
    expect_equal(
        "target.model_id",
        &target.target.model_id,
        "model.id",
        model_id,
    )?;
    let model_upstream = toml_string(&model, &["upstream", "repo_id"], "upstream.repo_id")?;
    expect_equal(
        "HF target upstream.repo_id",
        &target.upstream.repo_id,
        "model upstream.repo_id",
        model_upstream,
    )?;
    let framework = toml_string(&model, &["model", "framework"], "model.framework")?;
    expect_equal(
        "HF target canonical framework",
        &target.reference.canonical_framework,
        "model framework",
        framework,
    )?;

    let catalog_path = root.join("config/asr-catalog.json");
    let catalog: Catalog = serde_json::from_slice(&read(&catalog_path)?)?;
    if catalog.schema_version != 1 {
        return Err(contract(
            "config/asr-catalog.json schema_version must equal 1",
        ));
    }
    let profile_set = catalog
        .profile_sets
        .get(&target.runtime.profile_set)
        .ok_or_else(|| {
            contract(format!(
                "unknown profile set {:?}",
                target.runtime.profile_set
            ))
        })?;
    let variant = options
        .runtime_variant
        .as_deref()
        .filter(|value| !value.is_empty())
        .unwrap_or(&profile_set.default_variant);
    let profile_id = profile_set.variants.get(variant).ok_or_else(|| {
        contract(format!(
            "variant {variant:?} is not defined by profile set {:?}; available={:?}",
            target.runtime.profile_set,
            profile_set.variants.keys().collect::<Vec<_>>()
        ))
    })?;
    let decoder = &catalog
        .decoder_profiles
        .get(profile_id)
        .ok_or_else(|| contract(format!("unknown decoder profile {profile_id:?}")))?
        .decoder;
    require_nonempty("decoder", decoder)?;

    let route = if routes.is_empty() {
        Route {
            bucket: target.storage.bucket.clone(),
            model_repo: target.storage.model_repo.clone(),
        }
    } else {
        routes.get(&target_id).cloned().ok_or_else(|| {
            contract(format!(
                "HF target mapping does not contain target {target_id:?}"
            ))
        })?
    };

    Ok(ResolvedHfTarget {
        target_id,
        hf_bucket: route.bucket,
        hf_model_repo: route.model_repo.clone(),
        expected_development_repo_id: route.model_repo,
        expected_upstream_repo_id: target.upstream.repo_id.clone(),
        expected_tokenizer_repo_id: target.upstream.repo_id,
        expected_framework: target.reference.canonical_framework,
        profile_set: target.runtime.profile_set,
        runtime_variant: variant.to_owned(),
        runtime_profile: profile_id.clone(),
        decoder: decoder.clone(),
    })
}

pub fn append_github_file(path: &Path, values: &[(&str, &str)]) -> Result<()> {
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|source| HfError::Io {
            path: path.to_path_buf(),
            source,
        })?;
    for (key, value) in values {
        reject_line_breaks(key, value)?;
        writeln!(file, "{key}={value}").map_err(|source| HfError::Io {
            path: path.to_path_buf(),
            source,
        })?;
    }
    Ok(())
}

fn parse_routes(raw: Option<&str>) -> Result<BTreeMap<String, Route>> {
    let Some(raw) = raw.filter(|value| !value.trim().is_empty()) else {
        return Ok(BTreeMap::new());
    };
    let value: Value = serde_json::from_str(raw)?;
    let object = value
        .as_object()
        .ok_or_else(|| contract("HF target mapping root must be a JSON object"))?;
    let mut result = BTreeMap::new();
    let mut buckets = BTreeSet::new();
    for (target_id, entry) in object {
        validate_identifier(target_id)?;
        let entry = entry.as_object().ok_or_else(|| {
            contract(format!(
                "HF target mapping entry {target_id:?} must be a JSON object"
            ))
        })?;
        let bucket = json_string(entry.get("HF_BUCKET"), &format!("{target_id}.HF_BUCKET"))?;
        let model_repo = json_string(
            entry.get("HF_MODEL_REPO"),
            &format!("{target_id}.HF_MODEL_REPO"),
        )?;
        if !buckets.insert(bucket.clone()) {
            return Err(contract(format!(
                "HF_BUCKET {bucket:?} is assigned to multiple targets"
            )));
        }
        result.insert(target_id.clone(), Route { bucket, model_repo });
    }
    Ok(result)
}

fn target_from_bucket(bucket: &str, routes: &BTreeMap<String, Route>) -> Result<String> {
    require_nonempty("bucket", bucket)?;
    if routes.is_empty() {
        return Err(contract(
            "--bucket requires --targets-json because Bucket-to-target resolution is defined by the routing snapshot",
        ));
    }
    routes
        .iter()
        .find_map(|(target, route)| (route.bucket == bucket).then(|| target.clone()))
        .ok_or_else(|| {
            contract(format!(
                "HF_BUCKET {bucket:?} is not present in the current HF target mapping; available={:?}",
                routes.values().map(|route| &route.bucket).collect::<Vec<_>>()
            ))
        })
}

fn load_toml<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T> {
    let text = fs::read_to_string(path).map_err(|source| HfError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    toml::from_str(&text).map_err(|error| contract(format!("{}: {error}", path.display())))
}

fn read(path: &Path) -> Result<Vec<u8>> {
    fs::read(path).map_err(|source| HfError::Io {
        path: path.to_path_buf(),
        source,
    })
}

fn toml_string<'a>(value: &'a toml::Value, path: &[&str], name: &str) -> Result<&'a str> {
    let mut current = value;
    for part in path {
        current = current
            .get(*part)
            .ok_or_else(|| contract(format!("{name} is required")))?;
    }
    current
        .as_str()
        .and_then(|value| (!value.trim().is_empty()).then_some(value))
        .ok_or_else(|| contract(format!("{name} must be a non-empty string")))
}

fn json_string(value: Option<&Value>, name: &str) -> Result<String> {
    value
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| contract(format!("{name} must be a non-empty string")))
}

fn require_nonempty<'a>(name: &str, value: &'a str) -> Result<&'a str> {
    if value.trim().is_empty() {
        Err(contract(format!("{name} must be a non-empty string")))
    } else {
        Ok(value)
    }
}

fn validate_identifier(value: &str) -> Result<()> {
    require_nonempty("target id", value)?;
    if value.contains('/') || value.contains('\\') || value == "." || value == ".." {
        return Err(contract(format!("invalid target id {value:?}")));
    }
    Ok(())
}

fn expect_equal(left_name: &str, left: &str, right_name: &str, right: &str) -> Result<()> {
    if left != right {
        return Err(contract(format!(
            "{left_name} does not match {right_name}: {left:?} != {right:?}"
        )));
    }
    Ok(())
}

fn reject_line_breaks(key: &str, value: &str) -> Result<()> {
    if key.contains(['\n', '\r']) || value.contains(['\n', '\r']) {
        return Err(contract(format!(
            "GitHub environment/output value for {key:?} contains a line break"
        )));
    }
    Ok(())
}

fn contract(message: impl Into<String>) -> HfError {
    HfError::Contract(message.into())
}
