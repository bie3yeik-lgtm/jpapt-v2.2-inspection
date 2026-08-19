use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::{ContractError, Result};

const TARGET_ID: &str = "parakeet-tdt_ctc-0.6b-ja";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ProvenanceManifest {
    pub schema_version: u64,
    pub status: ProvenanceStatus,
    pub automation_consumption: bool,
    pub target_id: String,
    pub upstream: RepositoryIdentity,
    pub development_repo: RepositoryIdentity,
    pub assets: Vec<ProvenanceAsset>,
    pub blockers: Vec<String>,
    #[serde(default)]
    pub automation_enablement: Option<AutomationEnablement>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ProvenanceStatus {
    Incomplete,
    Complete,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RepositoryIdentity {
    pub repo_id: String,
    pub revision: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ProvenanceAsset {
    pub path: String,
    pub kind: String,
    pub sha256: String,
    pub origin: AssetOrigin,
    pub license: String,
    pub attribution: String,
    pub transformation: TransformationIdentity,
    #[serde(default)]
    pub candidate: Option<CandidateTransferIdentity>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AssetOrigin {
    pub repo_id: String,
    pub revision: String,
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TransformationIdentity {
    pub kind: String,
    pub tool: String,
    pub version: String,
    pub input_sha256: Option<String>,
    pub output_sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CandidateTransferIdentity {
    pub path: String,
    pub sha256: String,
    pub role: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AutomationEnablement {
    pub review_id: String,
    pub approved_at: String,
    pub approved_by: String,
    pub policy_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProvenanceValidation {
    pub manifest: ProvenanceManifest,
    pub fingerprint: String,
}

#[allow(dead_code)]
pub fn validate_provenance_file(
    path: impl AsRef<Path>,
    expected_target: &str,
) -> Result<ProvenanceValidation> {
    let path = path.as_ref();
    let text = fs::read_to_string(path).map_err(|source| ContractError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    let value: Value = serde_json::from_str(&text).map_err(|source| ContractError::Json {
        path: path.to_path_buf(),
        source,
    })?;
    validate_provenance_value(&value, expected_target)
}

pub fn validate_provenance_value(
    value: &Value,
    expected_target: &str,
) -> Result<ProvenanceValidation> {
    reject_unknown(
        value,
        "$",
        &[
            "schema_version",
            "status",
            "automation_consumption",
            "target_id",
            "upstream",
            "development_repo",
            "assets",
            "blockers",
            "automation_enablement",
        ],
    )?;
    reject_unknown(
        value.get("upstream").unwrap_or(&Value::Null),
        "upstream",
        &["repo_id", "revision"],
    )?;
    reject_unknown(
        value.get("development_repo").unwrap_or(&Value::Null),
        "development_repo",
        &["repo_id", "revision"],
    )?;
    let manifest: ProvenanceManifest = serde_json::from_value(value.clone())
        .map_err(|error| ContractError::validation(format!("invalid provenance shape: {error}")))?;
    if manifest.schema_version != 1 {
        return Err(ContractError::validation(
            "provenance.schema_version must equal 1",
        ));
    }
    if manifest.target_id != expected_target {
        return Err(ContractError::validation(format!(
            "provenance target mismatch: expected {expected_target:?}, got {:?}",
            manifest.target_id
        )));
    }
    if manifest.assets.is_empty() && matches!(manifest.status, ProvenanceStatus::Complete) {
        return Err(ContractError::validation(
            "complete provenance must contain assets",
        ));
    }
    if matches!(manifest.status, ProvenanceStatus::Complete) && !manifest.blockers.is_empty() {
        return Err(ContractError::validation(
            "complete provenance must not contain blockers",
        ));
    }
    validate_repository("upstream", &manifest.upstream, true)?;
    validate_repository("development_repo", &manifest.development_repo, false)?;

    let mut asset_paths = BTreeSet::new();
    let mut candidate_paths = BTreeSet::new();
    for (index, asset) in manifest.assets.iter().enumerate() {
        let label = format!("assets[{index}]");
        let raw_asset = value
            .pointer(&format!("/assets/{index}"))
            .ok_or_else(|| ContractError::validation(format!("{label} is missing")))?;
        reject_unknown(
            raw_asset,
            &label,
            &[
                "path",
                "kind",
                "sha256",
                "origin",
                "license",
                "attribution",
                "transformation",
                "candidate",
            ],
        )?;
        reject_unknown(
            raw_asset.get("origin").unwrap_or(&Value::Null),
            &format!("{label}.origin"),
            &["repo_id", "revision", "path"],
        )?;
        reject_unknown(
            raw_asset.get("transformation").unwrap_or(&Value::Null),
            &format!("{label}.transformation"),
            &["kind", "tool", "version", "input_sha256", "output_sha256"],
        )?;
        if let Some(candidate) = raw_asset.get("candidate") {
            reject_unknown(
                candidate,
                &format!("{label}.candidate"),
                &["path", "sha256", "role"],
            )?;
        }
        validate_relative_path(&format!("{label}.path"), &asset.path)?;
        if !asset_paths.insert(&asset.path) {
            return Err(ContractError::validation(format!(
                "duplicate asset path: {}",
                asset.path
            )));
        }
        if ![
            "weights",
            "config",
            "tokenizer",
            "script",
            "onnx",
            "metadata",
            "documentation",
            "third_party",
        ]
        .contains(&asset.kind.as_str())
        {
            return Err(ContractError::validation(format!(
                "{label}.kind is not supported"
            )));
        }
        validate_sha(&format!("{label}.sha256"), &asset.sha256)?;
        if asset.license.trim().is_empty() || asset.attribution.trim().is_empty() {
            return Err(ContractError::validation(format!(
                "{label} requires non-empty license and attribution"
            )));
        }
        validate_repository(&format!("{label}.origin"), &asset.origin.identity(), false)?;
        validate_relative_path(&format!("{label}.origin.path"), &asset.origin.path)?;
        validate_transformation(&label, &asset.transformation, &asset.sha256)?;
        if let Some(candidate) = &asset.candidate {
            validate_relative_path(&format!("{label}.candidate.path"), &candidate.path)?;
            if !candidate_paths.insert(&candidate.path) {
                return Err(ContractError::validation(format!(
                    "duplicate candidate path: {}",
                    candidate.path
                )));
            }
            validate_sha(&format!("{label}.candidate.sha256"), &candidate.sha256)?;
            if candidate.role.trim().is_empty() {
                return Err(ContractError::validation(format!(
                    "{label}.candidate.role is empty"
                )));
            }
            if candidate.sha256 != asset.sha256 {
                return Err(ContractError::validation(format!(
                    "PROVENANCE_CANDIDATE_TRANSFER_MISMATCH: {label}.candidate.sha256 must equal asset sha256"
                )));
            }
        }
    }
    if manifest.automation_consumption {
        let enablement = manifest.automation_enablement.as_ref().ok_or_else(|| {
            ContractError::validation("automation_consumption requires automation_enablement")
        })?;
        reject_unknown(
            value.get("automation_enablement").unwrap_or(&Value::Null),
            "automation_enablement",
            &["review_id", "approved_at", "approved_by", "policy_sha256"],
        )?;
        if enablement.review_id.trim().is_empty() || enablement.approved_by.trim().is_empty() {
            return Err(ContractError::validation(
                "automation_enablement review_id and approved_by are required",
            ));
        }
        if chrono::DateTime::parse_from_rfc3339(&enablement.approved_at).is_err() {
            return Err(ContractError::validation(
                "automation_enablement.approved_at must be RFC3339",
            ));
        }
        validate_sha(
            "automation_enablement.policy_sha256",
            &enablement.policy_sha256,
        )?;
    }
    let fingerprint = provenance_fingerprint(value)?;
    Ok(ProvenanceValidation {
        manifest,
        fingerprint,
    })
}

pub fn provenance_fingerprint(value: &Value) -> Result<String> {
    let canonical = canonical_json(value)?;
    Ok(format!("{:x}", Sha256::digest(canonical.as_bytes())))
}

#[allow(dead_code)]
pub fn require_execution_ready(manifest: &ProvenanceManifest) -> Result<()> {
    require_execution_ready_state(&manifest.status, manifest.automation_consumption)
}

#[allow(dead_code)]
pub fn require_execution_ready_state(
    status: &ProvenanceStatus,
    automation_consumption: bool,
) -> Result<()> {
    if !matches!(status, ProvenanceStatus::Complete) {
        return Err(ContractError::validation(
            "PROVENANCE_INCOMPLETE: canonical execution is disabled",
        ));
    }
    if !automation_consumption {
        return Err(ContractError::validation(
            "PROVENANCE_AUTOMATION_DISABLED: reviewed enablement is required",
        ));
    }
    Ok(())
}

fn validate_repository(label: &str, repo: &RepositoryIdentity, upstream: bool) -> Result<()> {
    if repo.repo_id.trim().is_empty() {
        return Err(ContractError::validation(format!(
            "{label}.repo_id is required"
        )));
    }
    let valid = is_hex_revision(&repo.revision)
        || (!upstream && repo.revision.starts_with("sha256:") && repo.revision.len() == 71)
        || (!upstream && repo.revision.starts_with("snapshot-") && repo.revision.len() > 9);
    if !valid {
        return Err(ContractError::validation(format!(
            "{label}.revision must be an immutable revision"
        )));
    }
    Ok(())
}

fn reject_unknown(value: &Value, label: &str, allowed: &[&str]) -> Result<()> {
    let object = value
        .as_object()
        .ok_or_else(|| ContractError::validation(format!("{label} must be an object")))?;
    for key in object.keys() {
        if !allowed.contains(&key.as_str()) {
            return Err(ContractError::validation(format!(
                "{label}.{key} is not allowed"
            )));
        }
    }
    Ok(())
}

fn validate_transformation(
    label: &str,
    value: &TransformationIdentity,
    asset_sha: &str,
) -> Result<()> {
    if !["copied", "converted", "generated", "modified"].contains(&value.kind.as_str())
        || value.tool.trim().is_empty()
        || value.version.trim().is_empty()
    {
        return Err(ContractError::validation(format!(
            "{label}.transformation is incomplete"
        )));
    }
    if value.kind != "copied" && value.input_sha256.is_none() {
        return Err(ContractError::validation(format!(
            "{label}.transformation.input_sha256 is required for non-copied assets"
        )));
    }
    if let Some(input) = &value.input_sha256 {
        validate_sha(&format!("{label}.transformation.input_sha256"), input)?;
    }
    validate_sha(
        &format!("{label}.transformation.output_sha256"),
        &value.output_sha256,
    )?;
    if value.output_sha256 != asset_sha {
        return Err(ContractError::validation(format!(
            "{label}.transformation.output_sha256 must equal asset sha256"
        )));
    }
    Ok(())
}

fn validate_relative_path(label: &str, value: &str) -> Result<()> {
    let path = Path::new(value);
    if value.trim().is_empty()
        || path.is_absolute()
        || value.contains('\\')
        || value
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(ContractError::validation(format!(
            "{label} must be a canonical relative path"
        )));
    }
    Ok(())
}

fn validate_sha(label: &str, value: &str) -> Result<()> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(ContractError::validation(format!(
            "{label} must be a lowercase SHA-256"
        )));
    }
    Ok(())
}

fn is_hex_revision(value: &str) -> bool {
    value.len() == 40 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn canonical_json(value: &Value) -> Result<String> {
    match value {
        Value::Null => Ok("null".into()),
        Value::Bool(value) => Ok(value.to_string()),
        Value::Number(value) => Ok(value.to_string()),
        Value::String(value) => serde_json::to_string(value)
            .map_err(|error| ContractError::validation(format!("canonical JSON string: {error}"))),
        Value::Array(values) => Ok(format!(
            "[{}]",
            values
                .iter()
                .map(canonical_json)
                .collect::<Result<Vec<_>>>()?
                .join(",")
        )),
        Value::Object(values) => {
            let sorted: BTreeMap<_, _> = values.iter().collect();
            let entries = sorted
                .into_iter()
                .map(|(key, value)| {
                    Ok(format!(
                        "{}:{}",
                        serde_json::to_string(key).unwrap(),
                        canonical_json(value)?
                    ))
                })
                .collect::<Result<Vec<_>>>()?;
            Ok(format!("{{{}}}", entries.join(",")))
        }
    }
}

impl AssetOrigin {
    fn identity(&self) -> RepositoryIdentity {
        RepositoryIdentity {
            repo_id: self.repo_id.clone(),
            revision: self.revision.clone(),
        }
    }
}

#[allow(dead_code)]
pub fn default_target_id() -> &'static str {
    TARGET_ID
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(name: &str) -> Value {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
        serde_json::from_slice(
            &fs::read(root.join("evaluation/provenance/fixtures").join(name)).unwrap(),
        )
        .unwrap()
    }

    #[test]
    fn accepts_incomplete_and_complete_fixtures() {
        assert_eq!(
            validate_provenance_value(&fixture("incomplete.json"), TARGET_ID)
                .unwrap()
                .manifest
                .status,
            ProvenanceStatus::Incomplete
        );
        assert_eq!(
            validate_provenance_value(&fixture("complete.json"), TARGET_ID)
                .unwrap()
                .manifest
                .status,
            ProvenanceStatus::Complete
        );
    }

    #[test]
    fn rejects_invalid_fixtures() {
        for name in [
            "invalid-missing-origin.json",
            "invalid-path.json",
            "invalid-automation.json",
            "invalid-candidate-transfer.json",
        ] {
            assert!(
                validate_provenance_value(&fixture(name), TARGET_ID).is_err(),
                "{name}"
            );
        }
    }

    #[test]
    fn incomplete_manifest_is_not_execution_ready() {
        let manifest = validate_provenance_value(&fixture("incomplete.json"), TARGET_ID)
            .unwrap()
            .manifest;
        assert!(require_execution_ready(&manifest).is_err());
    }

    #[test]
    fn fingerprint_is_independent_of_object_key_order() {
        let left = serde_json::json!({"b": 2, "a": 1});
        let right = serde_json::json!({"a": 1, "b": 2});
        assert_eq!(
            provenance_fingerprint(&left).unwrap(),
            provenance_fingerprint(&right).unwrap()
        );
    }
}
