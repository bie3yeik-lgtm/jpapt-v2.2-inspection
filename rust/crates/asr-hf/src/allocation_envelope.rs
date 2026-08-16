use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use asr_hf::{HfError, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct AllocationMetadata {
    pub source_repository: Option<String>,
    pub source_run_id: Option<String>,
    pub source_run_attempt: Option<String>,
    pub target_id: Option<String>,
    pub candidate_id: Option<String>,
    pub evaluation_id: Option<String>,
    pub provider_id: Option<String>,
    pub runtime_variant: Option<String>,
}

impl AllocationMetadata {
    pub fn to_compact_json(&self) -> Result<String> {
        let mut values = BTreeMap::<String, String>::new();
        insert_nonempty(&mut values, "source_repository", &self.source_repository);
        insert_nonempty(&mut values, "source_run_id", &self.source_run_id);
        insert_nonempty(
            &mut values,
            "source_run_attempt",
            &self.source_run_attempt,
        );
        insert_nonempty(&mut values, "target_id", &self.target_id);
        insert_nonempty(&mut values, "candidate_id", &self.candidate_id);
        insert_nonempty(&mut values, "evaluation_id", &self.evaluation_id);
        insert_nonempty(&mut values, "provider_id", &self.provider_id);
        insert_nonempty(&mut values, "runtime_variant", &self.runtime_variant);
        Ok(serde_json::to_string(&values)?)
    }
}

pub fn allocation_request_id(
    source_repository: Option<&str>,
    run_id: Option<&str>,
    run_attempt: Option<&str>,
) -> String {
    let repository = source_repository
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("local")
        .replace('/', "-");
    let run_id = run_id
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("manual");
    let run_attempt = run_attempt
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("0");
    let uuid = Uuid::new_v4().simple().to_string();
    let raw = format!("{repository}-{run_id}-{run_attempt}-{}", &uuid[..12]);
    sanitize_request_id(&raw)
}

fn sanitize_request_id(value: &str) -> String {
    value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '_' | '.' | '-') {
                ch
            } else {
                '-'
            }
        })
        .take(180)
        .collect()
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AllocationResponse<'a> {
    pub request_id: &'a str,
    pub allocation_id: &'a str,
    pub bucket: &'a str,
    pub collection: &'a str,
    pub catalog_id: &'a str,
    pub catalog_sha256: &'a str,
    pub prefix_key: &'a str,
    pub resolved_prefix: &'a str,
}

pub fn write_allocation_response(
    output: impl AsRef<Path>,
    response: &AllocationResponse<'_>,
) -> Result<()> {
    validate_response_fields(response)?;

    let mut catalog = BTreeMap::<String, Value>::new();
    catalog.insert("id".to_owned(), Value::String(response.catalog_id.to_owned()));
    catalog.insert(
        "sha256".to_owned(),
        Value::String(response.catalog_sha256.to_owned()),
    );

    let mut root = BTreeMap::<String, Value>::new();
    root.insert(
        "allocation_catalog".to_owned(),
        serde_json::to_value(catalog)?,
    );
    root.insert("bucket".to_owned(), Value::String(response.bucket.to_owned()));
    root.insert(
        "collection".to_owned(),
        Value::String(response.collection.to_owned()),
    );
    root.insert(
        "id".to_owned(),
        Value::String(response.allocation_id.to_owned()),
    );
    root.insert(
        "prefix_key".to_owned(),
        Value::String(response.prefix_key.to_owned()),
    );
    root.insert(
        "request_id".to_owned(),
        Value::String(response.request_id.to_owned()),
    );
    root.insert(
        "resolved_prefix".to_owned(),
        Value::String(response.resolved_prefix.to_owned()),
    );
    root.insert("schema_version".to_owned(), Value::from(3_u64));

    let path = output.as_ref().to_path_buf();
    let mut encoded = serde_json::to_string_pretty(&root)?;
    encoded.push('\n');
    fs::write(&path, encoded).map_err(|source| HfError::Io { path, source })
}

#[derive(Debug, Deserialize, Serialize)]
struct StoredAllocationResponse {
    schema_version: u32,
    request_id: String,
    id: String,
    bucket: String,
    collection: String,
    allocation_catalog: StoredAllocationCatalog,
    prefix_key: String,
    resolved_prefix: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct StoredAllocationCatalog {
    id: String,
    sha256: String,
}

pub fn read_allocation_response_id(path: impl AsRef<Path>) -> Result<String> {
    let path = path.as_ref().to_path_buf();
    let bytes = fs::read(&path).map_err(|source| HfError::Io {
        path: path.clone(),
        source,
    })?;
    let response: StoredAllocationResponse = serde_json::from_slice(&bytes)?;
    if response.schema_version != 3 {
        return Err(contract(format!(
            "allocation response schema_version must be 3, got {}",
            response.schema_version
        )));
    }
    for (name, value) in [
        ("request_id", response.request_id.as_str()),
        ("id", response.id.as_str()),
        ("bucket", response.bucket.as_str()),
        ("collection", response.collection.as_str()),
        ("allocation_catalog.id", response.allocation_catalog.id.as_str()),
        (
            "allocation_catalog.sha256",
            response.allocation_catalog.sha256.as_str(),
        ),
        ("prefix_key", response.prefix_key.as_str()),
        ("resolved_prefix", response.resolved_prefix.as_str()),
    ] {
        require_nonempty(name, value)?;
    }
    validate_collection(&response.collection)?;
    Ok(response.id)
}

fn validate_response_fields(response: &AllocationResponse<'_>) -> Result<()> {
    for (name, value) in [
        ("request_id", response.request_id),
        ("id", response.allocation_id),
        ("bucket", response.bucket),
        ("collection", response.collection),
        ("allocation_catalog.id", response.catalog_id),
        ("allocation_catalog.sha256", response.catalog_sha256),
        ("prefix_key", response.prefix_key),
        ("resolved_prefix", response.resolved_prefix),
    ] {
        require_nonempty(name, value)?;
    }
    validate_collection(response.collection)
}

fn validate_collection(value: &str) -> Result<()> {
    if matches!(value, "candidates" | "experiments" | "config") {
        Ok(())
    } else {
        Err(contract(format!(
            "allocation collection must be candidates, experiments, or config; got {value:?}"
        )))
    }
}

fn require_nonempty(name: &str, value: &str) -> Result<()> {
    if value.trim().is_empty() {
        Err(contract(format!("{name} must be a non-empty string")))
    } else {
        Ok(())
    }
}

fn insert_nonempty(values: &mut BTreeMap<String, String>, key: &str, value: &Option<String>) {
    if let Some(value) = value.as_deref().filter(|value| !value.is_empty()) {
        values.insert(key.to_owned(), value.to_owned());
    }
}

fn contract(message: impl Into<String>) -> HfError {
    HfError::Contract(message.into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn request_id_is_sanitized_and_bounded() {
        let id = allocation_request_id(Some("owner/repo with spaces"), Some("42"), Some("3"));
        assert!(id.starts_with("owner-repo-with-spaces-42-3-"));
        assert!(id.len() <= 180);
        assert!(
            id.chars()
                .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '.' | '-'))
        );
    }

    #[test]
    fn metadata_omits_empty_values() {
        let metadata = AllocationMetadata {
            source_repository: Some("owner/repo".into()),
            source_run_id: None,
            target_id: Some("target-a".into()),
            candidate_id: Some(String::new()),
            ..AllocationMetadata::default()
        };
        assert_eq!(
            metadata.to_compact_json().unwrap(),
            r#"{"source_repository":"owner/repo","target_id":"target-a"}"#
        );
    }
}
