use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::{ContractError, Result};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ResolvedProjectConfig {
    pub identity: String,
    pub model_id: String,
    pub provider_id: String,
    pub provider_ort_name: String,
    pub environment_id: String,
    pub evaluation_id: String,
    pub manifest: String,
    pub expected_sample_count: u64,
    pub sources: BTreeMap<String, String>,
    pub resolved: Value,
}

impl ResolvedProjectConfig {
    pub fn manifest_path(&self, repository_root: &Path) -> PathBuf {
        let path = PathBuf::from(&self.manifest);
        if path.is_absolute() {
            path
        } else {
            repository_root.join(path)
        }
    }
}

pub fn resolve_project_config(
    repository_root: impl AsRef<Path>,
    model_id: &str,
    provider_id: &str,
    evaluation_id: &str,
    environment_id: &str,
) -> Result<ResolvedProjectConfig> {
    let repository_root = repository_root.as_ref();
    require_identifier("model", model_id)?;
    require_identifier("provider", provider_id)?;
    require_identifier("evaluation", evaluation_id)?;
    require_identifier("environment", environment_id)?;

    let model_path = repository_root
        .join("config/models")
        .join(format!("{model_id}.toml"));
    let provider_path = repository_root
        .join("config/providers")
        .join(format!("{provider_id}.toml"));
    let environment_path = repository_root
        .join("config/environments")
        .join(format!("{environment_id}.toml"));
    let evaluation_path = repository_root
        .join("config/evaluation")
        .join(format!("{evaluation_id}.toml"));

    let model = load_toml(&model_path)?;
    let provider = load_toml(&provider_path)?;
    let environment = load_toml(&environment_path)?;
    let evaluation = load_toml(&evaluation_path)?;

    let actual_model_id = required_string(&model, &["model", "id"], "model.id")?;
    let actual_provider_id = required_string(&provider, &["provider", "id"], "provider.id")?;
    let actual_environment_id =
        required_string(&environment, &["environment", "id"], "environment.id")?;
    let actual_evaluation_id =
        required_string(&evaluation, &["evaluation", "id"], "evaluation.id")?;
    expect_id("model", model_id, actual_model_id, &model_path)?;
    expect_id("provider", provider_id, actual_provider_id, &provider_path)?;
    expect_id(
        "environment",
        environment_id,
        actual_environment_id,
        &environment_path,
    )?;
    expect_id(
        "evaluation",
        evaluation_id,
        actual_evaluation_id,
        &evaluation_path,
    )?;

    let provider_enabled = required_bool(&provider, &["provider", "enabled"], "provider.enabled")?;
    if !provider_enabled {
        return Err(ContractError::validation(format!(
            "provider is disabled: {provider_id}"
        )));
    }
    let provider_ort_name =
        required_string(&provider, &["provider", "ort_name"], "provider.ort_name")?;

    let supported_providers = required_string_array(
        &model,
        &["execution", "supported_providers"],
        "execution.supported_providers",
    )?;
    if !supported_providers.iter().any(|value| value == provider_id) {
        return Err(unsupported_provider(provider_id, environment_id));
    }
    let platform_key = ["execution", "platforms", environment_id];
    let platform_providers = required_string_array(
        &model,
        &platform_key,
        &format!("execution.platforms.{environment_id}"),
    )?;
    if !platform_providers.iter().any(|value| value == provider_id) {
        return Err(unsupported_provider(provider_id, environment_id));
    }
    let supported_os = required_string_array(
        &provider,
        &["provider", "supported_os"],
        "provider.supported_os",
    )?;
    if !supported_os.iter().any(|value| value == environment_id) {
        return Err(unsupported_provider(provider_id, environment_id));
    }

    if let Some(value) = get_path(&evaluation, &["ci", "supported_environments"]) {
        let supported = string_array(value, "ci.supported_environments")?;
        if !supported.iter().any(|value| value == environment_id) {
            return Err(ContractError::validation(format!(
                "evaluation suite does not support environment={environment_id:?}: evaluation={evaluation_id:?}"
            )));
        }
    }

    let manifest = required_string(
        &evaluation,
        &["evaluation", "manifest"],
        "evaluation.manifest",
    )?
    .to_owned();
    let expected_sample_count = required_positive_u64(
        &evaluation,
        &["evaluation", "expected_sample_count"],
        "evaluation.expected_sample_count",
    )?;
    let manifest_path = {
        let path = PathBuf::from(&manifest);
        if path.is_absolute() {
            path
        } else {
            repository_root.join(&path)
        }
    };
    if !manifest_path.is_file() {
        return Err(ContractError::validation(format!(
            "evaluation manifest does not exist: {}",
            manifest_path.display()
        )));
    }

    let mut sources = BTreeMap::new();
    sources.insert("model".into(), logical_source(repository_root, &model_path));
    sources.insert(
        "provider".into(),
        logical_source(repository_root, &provider_path),
    );
    sources.insert(
        "environment".into(),
        logical_source(repository_root, &environment_path),
    );
    sources.insert(
        "evaluation".into(),
        logical_source(repository_root, &evaluation_path),
    );

    let resolved = json!({
        "model": model,
        "provider": provider,
        "environment": environment,
        "evaluation": evaluation,
        "resolved": {
            "model_id": model_id,
            "provider_id": provider_id,
            "environment_id": environment_id,
            "evaluation_id": evaluation_id,
        }
    });

    Ok(ResolvedProjectConfig {
        identity: format!("{model_id}:{environment_id}:{provider_id}:{evaluation_id}"),
        model_id: model_id.to_owned(),
        provider_id: provider_id.to_owned(),
        provider_ort_name: provider_ort_name.to_owned(),
        environment_id: environment_id.to_owned(),
        evaluation_id: evaluation_id.to_owned(),
        manifest,
        expected_sample_count,
        sources,
        resolved,
    })
}

pub fn apply_runtime_overrides(
    config: &mut ResolvedProjectConfig,
    strict_provider: bool,
    optimization_level: &str,
) -> Result<()> {
    if !matches!(
        optimization_level,
        "configured" | "disable" | "basic" | "extended" | "all"
    ) {
        return Err(ContractError::validation(format!(
            "unsupported optimization level {optimization_level:?}"
        )));
    }
    let root = config
        .resolved
        .as_object_mut()
        .ok_or_else(|| ContractError::validation("resolved config root must be an object"))?;
    let provider = object_mut(root, "provider", "resolved.provider")?;
    if optimization_level != "configured" {
        object_mut(provider, "session", "resolved.provider.session")?.insert(
            "graph_optimization_level".into(),
            Value::String(optimization_level.to_owned()),
        );
    }
    if strict_provider {
        let validation = object_mut(provider, "validation", "resolved.provider.validation")?;
        validation.insert("strict_provider_mode".into(), Value::Bool(true));
        validation.insert("allow_cpu_fallback".into(), Value::Bool(false));
    }
    Ok(())
}

fn load_toml(path: &Path) -> Result<Value> {
    let text = fs::read_to_string(path).map_err(|source| ContractError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    let value: toml::Value = text.parse().map_err(|error: toml::de::Error| {
        ContractError::validation(format!("invalid TOML in {}: {error}", path.display()))
    })?;
    let value = serde_json::to_value(value)
        .map_err(|error| ContractError::validation(format!("{}: {error}", path.display())))?;
    let object = value.as_object().ok_or_else(|| {
        ContractError::validation(format!("TOML root must be a table: {}", path.display()))
    })?;
    let schema = object.get("schema_version").and_then(Value::as_i64);
    if schema != Some(1) {
        return Err(ContractError::validation(format!(
            "{}: schema_version must equal 1",
            path.display()
        )));
    }
    Ok(value)
}

fn get_path<'a>(value: &'a Value, path: &[&str]) -> Option<&'a Value> {
    let mut current = value;
    for part in path {
        current = current.as_object()?.get(*part)?;
    }
    Some(current)
}

fn required_string<'a>(value: &'a Value, path: &[&str], name: &str) -> Result<&'a str> {
    get_path(value, path)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| ContractError::validation(format!("{name} must be a non-empty string")))
}

fn required_bool(value: &Value, path: &[&str], name: &str) -> Result<bool> {
    get_path(value, path)
        .and_then(Value::as_bool)
        .ok_or_else(|| ContractError::validation(format!("{name} must be a boolean")))
}

fn required_positive_u64(value: &Value, path: &[&str], name: &str) -> Result<u64> {
    let value = get_path(value, path)
        .and_then(Value::as_u64)
        .ok_or_else(|| ContractError::validation(format!("{name} must be a positive integer")))?;
    if value == 0 {
        return Err(ContractError::validation(format!(
            "{name} must be a positive integer"
        )));
    }
    Ok(value)
}

fn required_string_array(value: &Value, path: &[&str], name: &str) -> Result<Vec<String>> {
    let value = get_path(value, path)
        .ok_or_else(|| ContractError::validation(format!("{name} is required")))?;
    string_array(value, name)
}

fn string_array(value: &Value, name: &str) -> Result<Vec<String>> {
    let values = value
        .as_array()
        .ok_or_else(|| ContractError::validation(format!("{name} must be an array")))?;
    values
        .iter()
        .enumerate()
        .map(|(index, value)| {
            value
                .as_str()
                .filter(|value| !value.trim().is_empty())
                .map(str::to_owned)
                .ok_or_else(|| {
                    ContractError::validation(format!(
                        "{name}[{index}] must be a non-empty string"
                    ))
                })
        })
        .collect()
}

fn object_mut<'a>(
    parent: &'a mut Map<String, Value>,
    key: &str,
    name: &str,
) -> Result<&'a mut Map<String, Value>> {
    if !parent.contains_key(key) {
        parent.insert(key.to_owned(), Value::Object(Map::new()));
    }
    parent
        .get_mut(key)
        .and_then(Value::as_object_mut)
        .ok_or_else(|| ContractError::validation(format!("{name} must be an object")))
}

fn expect_id(kind: &str, expected: &str, actual: &str, path: &Path) -> Result<()> {
    if expected != actual {
        return Err(ContractError::validation(format!(
            "{kind} filename and {kind}.id disagree: filename={expected:?}, actual={actual:?}, path={}",
            path.display()
        )));
    }
    Ok(())
}

fn require_identifier(kind: &str, value: &str) -> Result<()> {
    if value.trim().is_empty()
        || value.contains('/')
        || value.contains('\\')
        || value == "."
        || value == ".."
    {
        return Err(ContractError::validation(format!(
            "invalid {kind} configuration id {value:?}"
        )));
    }
    Ok(())
}

fn unsupported_provider(provider: &str, environment: &str) -> ContractError {
    ContractError::validation(format!(
        "provider {provider:?} is not supported for environment {environment:?}"
    ))
}

fn logical_source(repository_root: &Path, path: &Path) -> String {
    path.strip_prefix(repository_root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}
