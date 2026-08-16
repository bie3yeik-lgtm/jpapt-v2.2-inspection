use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::{HfError, Result};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AllocationCatalog {
    pub path: PathBuf,
    pub catalog_id: String,
    pub sha256: String,
    pub prefixes: BTreeMap<String, String>,
}

#[derive(Debug, Deserialize)]
struct AllocationCatalogDocument {
    schema_version: u32,
    catalog_id: String,
    prefixes: BTreeMap<String, String>,
}

impl AllocationCatalog {
    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref().to_path_buf();
        let bytes = fs::read(&path).map_err(|source| HfError::Io {
            path: path.clone(),
            source,
        })?;
        let raw: Value = serde_json::from_slice(&bytes)?;
        let document: AllocationCatalogDocument = serde_json::from_value(raw.clone())?;
        if document.schema_version != 1 {
            return Err(contract(
                "HF allocation catalog must be a schema_version=1 object",
            ));
        }
        let catalog_id = nonempty("catalog_id", document.catalog_id)?;
        if document.prefixes.is_empty() {
            return Err(contract("prefixes must be a non-empty object"));
        }
        let mut prefixes = BTreeMap::new();
        for (key, value) in document.prefixes {
            let key = nonempty("prefix key", key)?;
            let value = nonempty(&format!("prefixes.{key}"), value)?;
            validate_prefix(&value)?;
            prefixes.insert(key, value);
        }
        let canonical = canonical_json(&raw)?;
        let sha256 = format!("{:x}", Sha256::digest(canonical.as_bytes()));
        Ok(Self {
            path,
            catalog_id,
            sha256,
            prefixes,
        })
    }

    pub fn prefix(&self, key: &str) -> Result<&str> {
        self.prefixes.get(key).map(String::as_str).ok_or_else(|| {
            contract(format!(
                "unknown allocation prefix key {key:?}; available={:?}",
                self.prefixes.keys().collect::<Vec<_>>()
            ))
        })
    }

    pub fn candidate_prefix_key(&self, profile_set_id: &str) -> String {
        let key = format!("candidate.{profile_set_id}");
        if self.prefixes.contains_key(&key) {
            key
        } else {
            "candidate.default".to_owned()
        }
    }
}

pub fn load_repository_allocation_catalog(
    repository_root: impl AsRef<Path>,
) -> Result<AllocationCatalog> {
    AllocationCatalog::load(
        repository_root
            .as_ref()
            .join("config/hf-allocation-catalog.json"),
    )
}

pub fn next_sequence_id(prefix: &str, listing: &str) -> Result<String> {
    validate_prefix(prefix)?;
    let mut maximum = 0_u32;
    for raw in listing.lines() {
        let value = raw.trim();
        if value.is_empty() {
            continue;
        }
        let directory = value
            .split('/')
            .next()
            .unwrap_or_default()
            .trim_end_matches('/');
        let Some((_, suffix)) = directory.rsplit_once('-') else {
            continue;
        };
        if suffix.len() != 6 || !suffix.bytes().all(|byte| byte.is_ascii_digit()) {
            continue;
        }
        let parsed = suffix
            .parse::<u32>()
            .map_err(|error| contract(format!("invalid sequence suffix {suffix:?}: {error}")))?;
        maximum = maximum.max(parsed);
    }
    let next = maximum
        .checked_add(1)
        .ok_or_else(|| contract("six-digit HF sequence space is exhausted"))?;
    if next > 999_999 {
        return Err(contract("six-digit HF sequence space is exhausted"));
    }
    Ok(format!("{prefix}-{next:06}"))
}

pub fn write_allocation_readme(
    output: impl AsRef<Path>,
    allocation_id: &str,
    collection: &str,
    bucket: &str,
    prefix_key: &str,
    prefix: &str,
    sequence: &str,
    allocated_at: &str,
    metadata_json: &str,
) -> Result<()> {
    validate_prefix(prefix)?;
    for (name, value) in [
        ("allocation_id", allocation_id),
        ("collection", collection),
        ("bucket", bucket),
        ("prefix_key", prefix_key),
        ("sequence", sequence),
        ("allocated_at", allocated_at),
    ] {
        if value.trim().is_empty() {
            return Err(contract(format!("{name} must be a non-empty string")));
        }
    }
    let metadata: Value = serde_json::from_str(metadata_json)?;
    let object = metadata
        .as_object()
        .ok_or_else(|| contract("HF_ALLOCATION_METADATA_JSON must be a JSON object"))?;

    let mut lines = vec![
        format!("# {allocation_id}"),
        String::new(),
        "このディレクトリIDは中央Allocatorが自動採番しました。数値suffixは手動で再利用・変更しないでください。".to_owned(),
        String::new(),
        format!("- collection: `{collection}`"),
        format!("- bucket: `{bucket}`"),
        format!("- prefix_key: `{prefix_key}`"),
        format!("- resolved_prefix: `{prefix}`"),
        format!("- sequence: `{sequence}`"),
        format!("- allocated_at: `{allocated_at}`"),
    ];
    let mut keys = object.keys().collect::<Vec<_>>();
    keys.sort();
    for key in keys {
        let value = &object[key];
        if value.is_null() || value.as_str().is_some_and(str::is_empty) {
            continue;
        }
        let rendered = match value {
            Value::String(value) => value.clone(),
            _ => serde_json::to_string(value)?,
        };
        lines.push(format!("- {key}: `{rendered}`"));
    }
    lines.extend([
        String::new(),
        "prefixはconfig/hf-allocation-catalog.jsonで一元管理され、連番はcollection全体の最大suffix + 1で管理されます。".to_owned(),
        "targetとBucketの対応は採番時点のrouting snapshotであり、恒久的なidentityではありません。".to_owned(),
    ]);
    let path = output.as_ref().to_path_buf();
    fs::write(&path, format!("{}\n", lines.join("\n")))
        .map_err(|source| HfError::Io { path, source })
}

fn validate_prefix(prefix: &str) -> Result<()> {
    let bytes = prefix.as_bytes();
    if bytes.is_empty()
        || !bytes[0].is_ascii_alphanumeric()
        || !bytes[bytes.len() - 1].is_ascii_alphanumeric()
        || !bytes.iter().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'_' | b'-')
        })
    {
        return Err(contract(
            "prefix must contain only lowercase ASCII letters, digits, '.', '_', or '-', and must start/end with an alphanumeric character",
        ));
    }
    Ok(())
}

fn canonical_json(value: &Value) -> Result<String> {
    fn render(value: &Value, output: &mut String) -> std::result::Result<(), serde_json::Error> {
        match value {
            Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {
                output.push_str(&serde_json::to_string(value)?);
            }
            Value::Array(values) => {
                output.push('[');
                for (index, value) in values.iter().enumerate() {
                    if index != 0 {
                        output.push(',');
                    }
                    render(value, output)?;
                }
                output.push(']');
            }
            Value::Object(values) => {
                output.push('{');
                let mut keys = values.keys().collect::<Vec<_>>();
                keys.sort();
                for (index, key) in keys.iter().enumerate() {
                    if index != 0 {
                        output.push(',');
                    }
                    output.push_str(&serde_json::to_string(key)?);
                    output.push(':');
                    render(&values[*key], output)?;
                }
                output.push('}');
            }
        }
        Ok(())
    }

    let mut output = String::new();
    render(value, &mut output)?;
    Ok(output)
}

fn nonempty(name: &str, value: String) -> Result<String> {
    let value = value.trim();
    if value.is_empty() {
        Err(contract(format!("{name} must be a non-empty string")))
    } else {
        Ok(value.to_owned())
    }
}

fn contract(message: impl Into<String>) -> HfError {
    HfError::Contract(message.into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_collection_starts_at_one() {
        assert_eq!(next_sequence_id("export", "").unwrap(), "export-000001");
    }

    #[test]
    fn prefixes_share_collection_sequence() {
        let listing = "whisper-export-000001/README.md\nwhisper-export-000001/encoder.onnx\nctc-export-000004/README.md\ncpu-full-eval-000003/README.md\n";
        assert_eq!(
            next_sequence_id("whisper-export", listing).unwrap(),
            "whisper-export-000005"
        );
    }

    #[test]
    fn nested_numeric_filenames_do_not_influence_sequence() {
        let listing = "candidate-000002/logs/output-999999.txt\ncandidate-000002/artifacts/model-888888.onnx\n";
        assert_eq!(
            next_sequence_id("candidate", listing).unwrap(),
            "candidate-000003"
        );
    }

    #[test]
    fn invalid_prefix_is_rejected() {
        assert!(next_sequence_id("CPU Full Eval", "").is_err());
    }
}
