use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::{ContractError, Result};

const CONFIG_VERSION_PREFIX: &str = "config-";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CatalogReference {
    pub id: String,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RepoRevisionIdentity {
    pub repo_id: String,
    pub revision: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuntimeRevisionSnapshot {
    pub document_sha256: String,
    pub catalog: CatalogReference,
    pub profile_set: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReferenceRevisionSnapshot {
    pub document_sha256: String,
    pub development_artifact: RepoRevisionIdentity,
    pub upstream: RepoRevisionIdentity,
    pub tokenizer: RepoRevisionIdentity,
    pub reference_id: String,
    pub reference_revision: String,
    pub canonical_framework: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvaluationSchemaRevisionSnapshot {
    pub document_sha256: String,
    pub schema_id: String,
    pub schema_revision: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DatasetRevisionEntry {
    pub id: String,
    pub repo_id: String,
    pub revision: String,
    pub subset: String,
    pub split: String,
    pub sha256: String,
    pub manifest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DatasetsRevisionSnapshot {
    pub document_sha256: String,
    pub entries: Vec<DatasetRevisionEntry>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RevisionSnapshot {
    pub config_version: String,
    pub bundle_sha256: String,
    pub runtime: RuntimeRevisionSnapshot,
    pub reference: ReferenceRevisionSnapshot,
    pub evaluation_schema: EvaluationSchemaRevisionSnapshot,
    pub datasets: DatasetsRevisionSnapshot,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeResolution {
    pub variant: String,
    pub profile: String,
    pub decoder: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RevisionExpectations {
    pub development_repo_id: Option<String>,
    pub upstream_repo_id: Option<String>,
    pub tokenizer_repo_id: Option<String>,
    pub canonical_framework: Option<String>,
    pub profile_set: Option<String>,
    pub runtime_variant: Option<String>,
    pub runtime_profile: Option<String>,
    pub decoder: Option<String>,
}

impl RevisionExpectations {
    pub fn empty() -> Self {
        Self {
            development_repo_id: None,
            upstream_repo_id: None,
            tokenizer_repo_id: None,
            canonical_framework: None,
            profile_set: None,
            runtime_variant: None,
            runtime_profile: None,
            decoder: None,
        }
    }
}

#[derive(Debug, Clone)]
struct RevisionDocument {
    raw: Value,
    sha256: String,
}

#[derive(Debug, Clone)]
struct DecoderProfile {
    decoder: String,
}

#[derive(Debug, Clone)]
struct ProfileSet {
    variants: BTreeMap<String, String>,
    default_variant: String,
}

#[derive(Debug, Clone)]
struct Catalog {
    id: String,
    sha256: String,
    decoder_profiles: BTreeMap<String, DecoderProfile>,
    profile_sets: BTreeMap<String, ProfileSet>,
}

pub fn validate_revision_bundle(
    root: impl AsRef<Path>,
    expectations: &RevisionExpectations,
) -> Result<(RevisionSnapshot, RuntimeResolution)> {
    let root = root.as_ref();
    let repository_root = discover_repository_root(root)?;
    let catalog = load_catalog(&repository_root.join("config/asr-catalog.json"))?;

    let reference_doc = load_revision_document(&root.join("reference.json"))?;
    let evaluation_doc = load_revision_document(&root.join("evaluation-schema.json"))?;
    let datasets_doc = load_revision_document(&root.join("datasets-lock.json"))?;
    let runtime_doc = load_revision_document(&root.join("runtime.json"))?;
    let config_version = load_config_version(root)?;

    let reference = parse_reference(&reference_doc)?;
    let evaluation_schema = parse_evaluation_schema(&evaluation_doc)?;
    let datasets = parse_datasets(&datasets_doc)?;
    let (runtime, resolution) = parse_runtime(
        &runtime_doc,
        &catalog,
        expectations.runtime_variant.as_deref(),
    )?;

    expect_equal(
        "development_artifact.repo_id",
        &reference.development_artifact.repo_id,
        expectations.development_repo_id.as_deref(),
    )?;
    expect_equal(
        "upstream.repo_id",
        &reference.upstream.repo_id,
        expectations.upstream_repo_id.as_deref(),
    )?;
    expect_equal(
        "tokenizer.repo_id",
        &reference.tokenizer.repo_id,
        expectations.tokenizer_repo_id.as_deref(),
    )?;
    expect_equal(
        "canonical_framework",
        &reference.canonical_framework,
        expectations.canonical_framework.as_deref(),
    )?;
    expect_equal(
        "runtime.profile_set",
        &runtime.profile_set,
        expectations.profile_set.as_deref(),
    )?;
    expect_equal(
        &format!("runtime.variant[{}].profile", resolution.variant),
        &resolution.profile,
        expectations.runtime_profile.as_deref(),
    )?;
    expect_equal(
        &format!("runtime.variant[{}].decoder", resolution.variant),
        &resolution.decoder,
        expectations.decoder.as_deref(),
    )?;

    let mut bundle_digest = Sha256::new();
    for hash in [
        &reference_doc.sha256,
        &evaluation_doc.sha256,
        &datasets_doc.sha256,
        &runtime_doc.sha256,
    ] {
        bundle_digest.update(hash.as_bytes());
    }

    let snapshot = RevisionSnapshot {
        config_version,
        bundle_sha256: format!("{:x}", bundle_digest.finalize()),
        runtime,
        reference,
        evaluation_schema,
        datasets,
    };
    validate_snapshot(&snapshot)?;
    Ok((snapshot, resolution))
}

fn load_revision_document(path: &Path) -> Result<RevisionDocument> {
    let raw = read_json(path)?;
    let object = as_object(&raw, &path.display().to_string())?;
    if object.get("schema_version").and_then(Value::as_u64) != Some(1) {
        return Err(ContractError::validation(format!(
            "{}: schema_version must equal 1",
            path.display()
        )));
    }
    reject_nulls(&raw, &path.display().to_string())?;
    Ok(RevisionDocument {
        sha256: sha256_value(&raw)?,
        raw,
    })
}

fn load_config_version(root: &Path) -> Result<String> {
    let path = root.parent().unwrap_or(root).join("resolved.json");
    let raw = read_json(&path)?;
    let object = as_object(&raw, "resolved.json")?;
    exact_fields(
        object,
        "resolved.json",
        &["schema_version", "config_version"],
        &["current_version", "selection_source"],
    )?;
    if object.get("schema_version").and_then(Value::as_u64) != Some(1) {
        return Err(ContractError::validation(
            "resolved.json: schema_version must equal 1",
        ));
    }
    reject_nulls(&raw, "resolved.json")?;
    let value = required_string(object, "config_version", "resolved.json")?;
    if !valid_config_version(value) {
        return Err(ContractError::validation(format!(
            "resolved.json: config_version must match config-NNNNNN; got {value:?}"
        )));
    }
    if let Some(current_version) = optional_string(object, "current_version", "resolved.json")?
        && !valid_config_version(current_version)
    {
        return Err(ContractError::validation(format!(
            "resolved.json: current_version must match config-NNNNNN; got {current_version:?}"
        )));
    }
    if let Some(selection_source) = optional_string(object, "selection_source", "resolved.json")?
        && !matches!(selection_source, "current" | "override")
    {
        return Err(ContractError::validation(format!(
            "resolved.json: selection_source must be current or override; got {selection_source:?}"
        )));
    }
    Ok(value.to_owned())
}

fn parse_reference(document: &RevisionDocument) -> Result<ReferenceRevisionSnapshot> {
    let raw = as_object(&document.raw, "reference.json")?;
    exact_fields(
        raw,
        "reference.json",
        &[
            "schema_version",
            "development_artifact",
            "upstream",
            "tokenizer",
            "reference",
        ],
        &[],
    )?;
    let development_artifact = parse_repo_identity(raw, "development_artifact", "reference.json")?;
    let upstream = parse_repo_identity(raw, "upstream", "reference.json")?;
    let tokenizer = parse_repo_identity(raw, "tokenizer", "reference.json")?;
    let reference = required_object(raw, "reference", "reference.json")?;
    exact_fields(
        reference,
        "reference.json.reference",
        &["id", "revision", "canonical_framework"],
        &[],
    )?;
    Ok(ReferenceRevisionSnapshot {
        document_sha256: document.sha256.clone(),
        development_artifact,
        upstream,
        tokenizer,
        reference_id: required_string(reference, "id", "reference.json.reference")?.to_owned(),
        reference_revision: required_string(reference, "revision", "reference.json.reference")?
            .to_owned(),
        canonical_framework: required_string(
            reference,
            "canonical_framework",
            "reference.json.reference",
        )?
        .to_owned(),
    })
}

fn parse_evaluation_schema(
    document: &RevisionDocument,
) -> Result<EvaluationSchemaRevisionSnapshot> {
    let raw = as_object(&document.raw, "evaluation-schema.json")?;
    exact_fields(
        raw,
        "evaluation-schema.json",
        &["schema_version", "schema"],
        &[],
    )?;
    let schema = required_object(raw, "schema", "evaluation-schema.json")?;
    exact_fields(
        schema,
        "evaluation-schema.json.schema",
        &["id", "revision"],
        &[],
    )?;
    Ok(EvaluationSchemaRevisionSnapshot {
        document_sha256: document.sha256.clone(),
        schema_id: required_string(schema, "id", "evaluation-schema.json.schema")?.to_owned(),
        schema_revision: required_string(schema, "revision", "evaluation-schema.json.schema")?
            .to_owned(),
    })
}

fn parse_datasets(document: &RevisionDocument) -> Result<DatasetsRevisionSnapshot> {
    let raw = as_object(&document.raw, "datasets-lock.json")?;
    exact_fields(
        raw,
        "datasets-lock.json",
        &["schema_version", "datasets"],
        &[],
    )?;
    let datasets = raw
        .get("datasets")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            ContractError::validation("datasets-lock.json: datasets must be an array")
        })?;
    let mut entries = Vec::with_capacity(datasets.len());
    let mut ids = BTreeSet::new();
    for (index, value) in datasets.iter().enumerate() {
        let name = format!("datasets-lock.json.datasets[{index}]");
        let object = as_object(value, &name)?;
        exact_fields(
            object,
            &name,
            &["id", "repo_id", "revision"],
            &["subset", "split", "sha256", "manifest"],
        )?;
        let id = required_string(object, "id", &name)?.to_owned();
        if !ids.insert(id.clone()) {
            return Err(ContractError::validation(
                "datasets-lock.json: duplicate dataset IDs are not allowed",
            ));
        }
        let sha256 = required_string(object, "sha256", &name).map_err(|_| {
            ContractError::validation(format!(
                "datasets-lock entry {id:?} requires sha256 before execution"
            ))
        })?;
        require_sha256(&format!("{name}.sha256"), sha256)?;
        let manifest = required_string(object, "manifest", &name).map_err(|_| {
            ContractError::validation(format!(
                "datasets-lock entry {id:?} requires manifest before execution"
            ))
        })?;
        entries.push(DatasetRevisionEntry {
            id,
            repo_id: required_string(object, "repo_id", &name)?.to_owned(),
            revision: required_string(object, "revision", &name)?.to_owned(),
            subset: optional_string(object, "subset", &name)?
                .unwrap_or("default")
                .to_owned(),
            split: optional_string(object, "split", &name)?
                .unwrap_or("default")
                .to_owned(),
            sha256: sha256.to_ascii_lowercase(),
            manifest: manifest.to_owned(),
        });
    }
    Ok(DatasetsRevisionSnapshot {
        document_sha256: document.sha256.clone(),
        entries,
    })
}

fn parse_runtime(
    document: &RevisionDocument,
    catalog: &Catalog,
    requested_variant: Option<&str>,
) -> Result<(RuntimeRevisionSnapshot, RuntimeResolution)> {
    let raw = as_object(&document.raw, "runtime.json")?;
    exact_fields(
        raw,
        "runtime.json",
        &["schema_version", "catalog", "profile_set"],
        &[],
    )?;
    let catalog_ref = required_object(raw, "catalog", "runtime.json")?;
    exact_fields(catalog_ref, "runtime.json.catalog", &["id", "sha256"], &[])?;
    let catalog_id = required_string(catalog_ref, "id", "runtime.json.catalog")?;
    let catalog_sha = required_string(catalog_ref, "sha256", "runtime.json.catalog")?;
    require_sha256("runtime.json.catalog.sha256", catalog_sha)?;
    if catalog_id != catalog.id {
        return Err(ContractError::validation(format!(
            "runtime.json catalog id mismatch: lock={catalog_id:?}, repository={:?}",
            catalog.id
        )));
    }
    if !catalog_sha.eq_ignore_ascii_case(&catalog.sha256) {
        return Err(ContractError::validation(
            "runtime.json catalog SHA-256 does not match config/asr-catalog.json",
        ));
    }
    let profile_set_id = required_string(raw, "profile_set", "runtime.json")?;
    let profile_set = catalog.profile_sets.get(profile_set_id).ok_or_else(|| {
        ContractError::validation(format!("unknown profile set {profile_set_id:?}"))
    })?;
    let variant = requested_variant.unwrap_or(&profile_set.default_variant);
    let profile_id = profile_set.variants.get(variant).ok_or_else(|| {
        ContractError::validation(format!(
            "unknown runtime variant {variant:?}; available={:?}",
            profile_set.variants.keys().collect::<Vec<_>>()
        ))
    })?;
    let profile = catalog.decoder_profiles.get(profile_id).ok_or_else(|| {
        ContractError::validation(format!("unknown decoder profile {profile_id:?}"))
    })?;
    Ok((
        RuntimeRevisionSnapshot {
            document_sha256: document.sha256.clone(),
            catalog: CatalogReference {
                id: catalog_id.to_owned(),
                sha256: catalog_sha.to_ascii_lowercase(),
            },
            profile_set: profile_set_id.to_owned(),
        },
        RuntimeResolution {
            variant: variant.to_owned(),
            profile: profile_id.clone(),
            decoder: profile.decoder.clone(),
        },
    ))
}

fn load_catalog(path: &Path) -> Result<Catalog> {
    let raw = read_json(path)?;
    let object = as_object(&raw, "config/asr-catalog.json")?;
    if object.get("schema_version").and_then(Value::as_u64) != Some(1) {
        return Err(ContractError::validation(
            "ASR catalog must be a schema_version=1 object",
        ));
    }
    let id = required_string(object, "catalog_id", "config/asr-catalog.json")?.to_owned();
    let profiles_raw = required_object(object, "decoder_profiles", "config/asr-catalog.json")?;
    let mut decoder_profiles = BTreeMap::new();
    for (profile_id, value) in profiles_raw {
        if profile_id.trim().is_empty() {
            return Err(ContractError::validation(
                "decoder_profiles keys must be non-empty strings",
            ));
        }
        let profile = as_object(value, &format!("decoder_profiles.{profile_id}"))?;
        decoder_profiles.insert(
            profile_id.clone(),
            DecoderProfile {
                decoder: required_string(
                    profile,
                    "decoder",
                    &format!("decoder_profiles.{profile_id}"),
                )?
                .to_owned(),
            },
        );
    }
    let sets_raw = required_object(object, "profile_sets", "config/asr-catalog.json")?;
    let mut profile_sets = BTreeMap::new();
    for (set_id, value) in sets_raw {
        if set_id.trim().is_empty() {
            return Err(ContractError::validation(
                "profile_sets keys must be non-empty strings",
            ));
        }
        let set = as_object(value, &format!("profile_sets.{set_id}"))?;
        let variants_raw = required_object(set, "variants", &format!("profile_sets.{set_id}"))?;
        let mut variants = BTreeMap::new();
        for (variant, profile_value) in variants_raw {
            let profile_id = profile_value
                .as_str()
                .filter(|value| !value.trim().is_empty())
                .ok_or_else(|| {
                    ContractError::validation(format!(
                        "profile_sets.{set_id}.variants.{variant} must be a non-empty string"
                    ))
                })?;
            if !decoder_profiles.contains_key(profile_id) {
                return Err(ContractError::validation(format!(
                    "profile set {set_id:?} references unknown decoder profile {profile_id:?}"
                )));
            }
            variants.insert(variant.clone(), profile_id.to_owned());
        }
        let default_variant =
            required_string(set, "default_variant", &format!("profile_sets.{set_id}"))?;
        if !variants.contains_key(default_variant) {
            return Err(ContractError::validation(format!(
                "profile_sets.{set_id}.default_variant must be one of {:?}",
                variants.keys().collect::<Vec<_>>()
            )));
        }
        profile_sets.insert(
            set_id.clone(),
            ProfileSet {
                variants,
                default_variant: default_variant.to_owned(),
            },
        );
    }
    Ok(Catalog {
        id,
        sha256: sha256_value(&raw)?,
        decoder_profiles,
        profile_sets,
    })
}

fn validate_snapshot(snapshot: &RevisionSnapshot) -> Result<()> {
    if !valid_config_version(&snapshot.config_version) {
        return Err(ContractError::validation(
            "revisions.config_version must match config-NNNNNN",
        ));
    }
    require_sha256("revisions.bundle_sha256", &snapshot.bundle_sha256)?;
    require_sha256(
        "revisions.runtime.document_sha256",
        &snapshot.runtime.document_sha256,
    )?;
    require_sha256(
        "revisions.reference.document_sha256",
        &snapshot.reference.document_sha256,
    )?;
    require_sha256(
        "revisions.evaluation_schema.document_sha256",
        &snapshot.evaluation_schema.document_sha256,
    )?;
    require_sha256(
        "revisions.datasets.document_sha256",
        &snapshot.datasets.document_sha256,
    )?;
    let mut ids = BTreeSet::new();
    for entry in &snapshot.datasets.entries {
        require_sha256("revisions.datasets.entries.sha256", &entry.sha256)?;
        if !ids.insert(&entry.id) {
            return Err(ContractError::validation(format!(
                "duplicate dataset revision id: {}",
                entry.id
            )));
        }
    }
    Ok(())
}

fn parse_repo_identity(
    parent: &Map<String, Value>,
    key: &str,
    document: &str,
) -> Result<RepoRevisionIdentity> {
    let name = format!("{document}.{key}");
    let object = required_object(parent, key, document)?;
    exact_fields(object, &name, &["repo_id", "revision"], &[])?;
    Ok(RepoRevisionIdentity {
        repo_id: required_string(object, "repo_id", &name)?.to_owned(),
        revision: required_string(object, "revision", &name)?.to_owned(),
    })
}

fn discover_repository_root(start: &Path) -> Result<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(current) = start.canonicalize() {
        candidates.push(current);
    } else {
        candidates.push(start.to_path_buf());
    }
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd);
    }
    for candidate in candidates {
        for parent in candidate.ancestors() {
            if parent.join("config/asr-catalog.json").is_file() {
                return Ok(parent.to_path_buf());
            }
        }
    }
    Err(ContractError::validation(
        "could not locate repository config/asr-catalog.json",
    ))
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

fn sha256_value(value: &Value) -> Result<String> {
    let bytes = serde_json::to_vec(value).map_err(|error| {
        ContractError::validation(format!("failed to canonicalize JSON value: {error}"))
    })?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn reject_nulls(value: &Value, path: &str) -> Result<()> {
    match value {
        Value::Null => Err(ContractError::validation(format!(
            "null values are not allowed: {path}"
        ))),
        Value::Array(values) => {
            for (index, item) in values.iter().enumerate() {
                reject_nulls(item, &format!("{path}[{index}]"))?;
            }
            Ok(())
        }
        Value::Object(values) => {
            for (key, item) in values {
                reject_nulls(item, &format!("{path}.{key}"))?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn as_object<'a>(value: &'a Value, name: &str) -> Result<&'a Map<String, Value>> {
    value
        .as_object()
        .ok_or_else(|| ContractError::validation(format!("{name} must be an object")))
}

fn required_object<'a>(
    value: &'a Map<String, Value>,
    key: &str,
    name: &str,
) -> Result<&'a Map<String, Value>> {
    value
        .get(key)
        .and_then(Value::as_object)
        .ok_or_else(|| ContractError::validation(format!("{name}.{key} must be an object")))
}

fn exact_fields(
    value: &Map<String, Value>,
    name: &str,
    required: &[&str],
    optional: &[&str],
) -> Result<()> {
    for key in required {
        if !value.contains_key(*key) {
            return Err(ContractError::validation(format!(
                "{name} is missing required field {key:?}"
            )));
        }
    }
    for key in value.keys() {
        if !required.contains(&key.as_str()) && !optional.contains(&key.as_str()) {
            return Err(ContractError::validation(format!(
                "{name} contains unsupported field {key:?}"
            )));
        }
    }
    Ok(())
}

fn required_string<'a>(value: &'a Map<String, Value>, key: &str, name: &str) -> Result<&'a str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            ContractError::validation(format!("{name}.{key} must be a non-empty string"))
        })
}

fn optional_string<'a>(
    value: &'a Map<String, Value>,
    key: &str,
    name: &str,
) -> Result<Option<&'a str>> {
    match value.get(key) {
        None => Ok(None),
        Some(item) => item
            .as_str()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(Some)
            .ok_or_else(|| {
                ContractError::validation(format!(
                    "{name}.{key} must be a non-empty string when present"
                ))
            }),
    }
}

fn require_sha256(name: &str, value: &str) -> Result<()> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(ContractError::validation(format!(
            "{name} must be a 64-character SHA-256"
        )));
    }
    Ok(())
}

fn valid_config_version(value: &str) -> bool {
    value.len() == 13
        && value.starts_with(CONFIG_VERSION_PREFIX)
        && value[CONFIG_VERSION_PREFIX.len()..]
            .bytes()
            .all(|byte| byte.is_ascii_digit())
}

fn expect_equal(label: &str, actual: &str, expected: Option<&str>) -> Result<()> {
    if let Some(expected) = expected
        && actual != expected
    {
        return Err(ContractError::validation(format!(
            "{label} mismatch: expected={expected:?}, actual={actual:?}"
        )));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_version_contract_is_strict() {
        assert!(valid_config_version("config-000001"));
        assert!(!valid_config_version("config-1"));
        assert!(!valid_config_version("config-000001x"));
    }

    #[test]
    fn expectation_mismatch_fails() {
        let error = expect_equal("decoder", "ctc", Some("tdt")).unwrap_err();
        assert!(error.to_string().contains("decoder mismatch"));
    }
}
