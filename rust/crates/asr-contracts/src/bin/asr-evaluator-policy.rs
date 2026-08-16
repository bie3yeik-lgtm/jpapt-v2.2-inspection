use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use serde::Deserialize;
use serde_json::Value;

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-evaluator-policy: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut repository_root = PathBuf::from(".");
    let mut evaluator = None;
    let mut decoder = None;
    let mut provider = None;
    let mut runtime_variant = None;
    let mut candidate_contract = None;

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--repository-root" => {
                repository_root = PathBuf::from(take_value(&mut args, "--repository-root")?)
            }
            "--evaluator" => evaluator = Some(take_value(&mut args, "--evaluator")?),
            "--decoder" => decoder = Some(take_value(&mut args, "--decoder")?),
            "--provider" => provider = Some(take_value(&mut args, "--provider")?),
            "--runtime-variant" => {
                runtime_variant = Some(take_value(&mut args, "--runtime-variant")?)
            }
            "--candidate-contract" => {
                candidate_contract = Some(PathBuf::from(take_value(
                    &mut args,
                    "--candidate-contract",
                )?))
            }
            other => return Err(format!("unsupported argument {other:?}\n{}", usage())),
        }
    }

    let evaluator = evaluator.ok_or_else(|| "--evaluator is required".to_owned())?;
    let decoder = decoder.ok_or_else(|| "--decoder is required".to_owned())?;
    validate_evaluator_policy(
        &repository_root,
        &evaluator,
        &decoder,
        provider.as_deref(),
        runtime_variant.as_deref(),
        candidate_contract.as_deref(),
    )
}

fn usage() -> &'static str {
    "usage: asr-evaluator-policy --evaluator <id> --decoder <decoder> [--provider <provider>] [--runtime-variant <variant>] [--candidate-contract <candidate-contract.json>] [--repository-root <repo>]"
}

fn validate_evaluator_policy(
    repository_root: &Path,
    evaluator_id: &str,
    decoder: &str,
    provider: Option<&str>,
    runtime_variant: Option<&str>,
    candidate_contract_path: Option<&Path>,
) -> Result<(), String> {
    let path = repository_root
        .join("config/evaluators")
        .join(format!("{evaluator_id}.toml"));
    let text = fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))?;
    let document: EvaluatorDocument = toml::from_str(&text)
        .map_err(|error| format!("invalid evaluator capability file {}: {error}", path.display()))?;
    document.validate(evaluator_id, decoder, provider)?;

    let candidate = if let Some(path) = candidate_contract_path {
        let candidate = CandidateContract::load(path)?;
        candidate.validate()?;
        if candidate.decoder != decoder {
            return Err(format!(
                "candidate decoder mismatch: expected={decoder:?}, candidate={:?}, variant={:?}",
                candidate.decoder, candidate.variant
            ));
        }
        if let Some(expected_variant) = runtime_variant
            && candidate.variant != expected_variant
        {
            return Err(format!(
                "candidate runtime variant mismatch: expected={expected_variant:?}, candidate={:?}",
                candidate.variant
            ));
        }
        document.validate_candidate(decoder, &candidate)?;
        Some(candidate)
    } else {
        None
    };

    let provider = provider.unwrap_or("not-checked");
    if let Some(candidate) = candidate {
        println!(
            "Evaluator capability OK: evaluator={evaluator_id}, decoder={decoder}, provider={provider}, runtime_variant={}, artifact_contract={}, features={}",
            candidate.variant,
            candidate.artifact_contract,
            serde_json::to_string(&candidate.features).map_err(|error| error.to_string())?
        );
    } else {
        println!(
            "Evaluator capability OK: evaluator={evaluator_id}, decoder={decoder}, provider={provider}"
        );
    }
    Ok(())
}

#[derive(Debug, Deserialize)]
struct EvaluatorDocument {
    schema_version: u32,
    evaluator: EvaluatorIdentity,
    capabilities: EvaluatorCapabilities,
    #[serde(default)]
    decoder_features: BTreeMap<String, BTreeMap<String, bool>>,
}

#[derive(Debug, Deserialize)]
struct EvaluatorIdentity {
    id: String,
    implementation: String,
    backend: String,
}

#[derive(Debug, Deserialize)]
struct EvaluatorCapabilities {
    supported_decoders: Vec<String>,
    #[serde(default)]
    supported_providers: Vec<String>,
    #[serde(default)]
    supported_artifact_contracts: Vec<String>,
}

impl EvaluatorDocument {
    fn validate(&self, requested_id: &str, decoder: &str, provider: Option<&str>) -> Result<(), String> {
        if self.schema_version != 2 {
            return Err("evaluator capability schema_version must equal 2".to_owned());
        }
        require_nonempty("evaluator.id", &self.evaluator.id)?;
        require_nonempty("evaluator.implementation", &self.evaluator.implementation)?;
        require_nonempty("evaluator.backend", &self.evaluator.backend)?;
        validate_string_list(
            "capabilities.supported_decoders",
            &self.capabilities.supported_decoders,
            true,
        )?;
        validate_string_list(
            "capabilities.supported_providers",
            &self.capabilities.supported_providers,
            false,
        )?;
        validate_string_list(
            "capabilities.supported_artifact_contracts",
            &self.capabilities.supported_artifact_contracts,
            false,
        )?;
        if self.evaluator.id != requested_id {
            return Err(format!(
                "evaluator id mismatch: requested={requested_id:?}, configured={:?}",
                self.evaluator.id
            ));
        }
        if !self.capabilities.supported_decoders.iter().any(|item| item == decoder) {
            return Err(format!(
                "evaluator capability mismatch: evaluator={requested_id:?}, decoder={decoder:?}, supported={:?}",
                self.capabilities.supported_decoders
            ));
        }
        if !self.decoder_features.contains_key(decoder) {
            return Err(format!(
                "evaluator has no decoder_features table for supported decoder {decoder:?}"
            ));
        }
        if let Some(provider) = provider
            && !self.capabilities.supported_providers.is_empty()
            && !self
                .capabilities
                .supported_providers
                .iter()
                .any(|item| item == provider)
        {
            return Err(format!(
                "evaluator provider mismatch: evaluator={requested_id:?}, provider={provider:?}, supported={:?}",
                self.capabilities.supported_providers
            ));
        }
        Ok(())
    }

    fn validate_candidate(&self, decoder: &str, candidate: &CandidateContract) -> Result<(), String> {
        if !self.capabilities.supported_artifact_contracts.is_empty()
            && !self
                .capabilities
                .supported_artifact_contracts
                .iter()
                .any(|item| item == &candidate.artifact_contract)
        {
            return Err(format!(
                "candidate artifact contract is unsupported: contract={:?}, supported={:?}",
                candidate.artifact_contract, self.capabilities.supported_artifact_contracts
            ));
        }
        let features = self
            .decoder_features
            .get(decoder)
            .expect("decoder feature table checked");
        for (feature, required) in &candidate.features {
            if *required && !features.get(feature).copied().unwrap_or(false) {
                return Err(format!(
                    "candidate requires unsupported evaluator feature: feature={feature:?}, decoder={decoder:?}, evaluator={:?}",
                    self.evaluator.id
                ));
            }
        }
        Ok(())
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CandidateContract {
    schema_version: u32,
    candidate_root: String,
    candidate_id: String,
    profile_set: String,
    variant: String,
    profile: String,
    decoder: String,
    artifact_contract: String,
    catalog: CandidateCatalog,
    bundle_sha256: String,
    artifacts: BTreeMap<String, CandidateArtifact>,
    tokenizer: Option<CandidateTokenizer>,
    features: BTreeMap<String, bool>,
    runtime_contract: CandidateRuntimeContract,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CandidateCatalog {
    id: String,
    sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CandidateArtifact {
    path: String,
    sha256: String,
    size_bytes: u64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CandidateTokenizer {
    kind: String,
    path: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CandidateRuntimeContract {
    decoder: String,
    input_kind: String,
    io: Value,
    decoder_config: Value,
}

impl CandidateContract {
    fn load(path: &Path) -> Result<Self, String> {
        let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
        serde_json::from_str(&text)
            .map_err(|error| format!("invalid generated candidate contract {}: {error}", path.display()))
    }

    fn validate(&self) -> Result<(), String> {
        if self.schema_version != 1 {
            return Err("generated candidate schema_version must equal 1".to_owned());
        }
        for (name, value) in [
            ("candidate_root", self.candidate_root.as_str()),
            ("candidate_id", self.candidate_id.as_str()),
            ("profile_set", self.profile_set.as_str()),
            ("variant", self.variant.as_str()),
            ("profile", self.profile.as_str()),
            ("decoder", self.decoder.as_str()),
            ("artifact_contract", self.artifact_contract.as_str()),
            ("catalog.id", self.catalog.id.as_str()),
            ("bundle_sha256", self.bundle_sha256.as_str()),
            ("catalog.sha256", self.catalog.sha256.as_str()),
            ("runtime_contract.decoder", self.runtime_contract.decoder.as_str()),
            ("runtime_contract.input_kind", self.runtime_contract.input_kind.as_str()),
        ] {
            require_nonempty(name, value)?;
        }
        require_sha256("bundle_sha256", &self.bundle_sha256)?;
        require_sha256("catalog.sha256", &self.catalog.sha256)?;
        if self.artifacts.is_empty() {
            return Err("candidate artifacts must be non-empty".to_owned());
        }
        for (role, artifact) in &self.artifacts {
            require_nonempty("artifact role", role)?;
            require_nonempty(&format!("artifacts.{role}.path"), &artifact.path)?;
            require_sha256(&format!("artifacts.{role}.sha256"), &artifact.sha256)?;
            if artifact.size_bytes == 0 {
                return Err(format!("artifacts.{role}.size_bytes must be positive"));
            }
        }
        if let Some(tokenizer) = &self.tokenizer {
            require_nonempty("tokenizer.kind", &tokenizer.kind)?;
            require_nonempty("tokenizer.path", &tokenizer.path)?;
        }
        if self.runtime_contract.decoder != self.decoder {
            return Err("candidate decoder must equal runtime_contract.decoder".to_owned());
        }
        if !matches!(self.runtime_contract.io, Value::Object(_)) {
            return Err("runtime_contract.io must be an object".to_owned());
        }
        if !matches!(self.runtime_contract.decoder_config, Value::Object(_)) {
            return Err("runtime_contract.decoder_config must be an object".to_owned());
        }
        Ok(())
    }
}

fn validate_string_list(name: &str, values: &[String], required: bool) -> Result<(), String> {
    if required && values.is_empty() {
        return Err(format!("{name} must be a non-empty string list"));
    }
    if values.iter().any(|value| value.trim().is_empty()) {
        return Err(format!("{name} must contain only non-empty strings"));
    }
    Ok(())
}

fn require_nonempty(name: &str, value: &str) -> Result<(), String> {
    if value.trim().is_empty() {
        Err(format!("{name} must be a non-empty string"))
    } else {
        Ok(())
    }
}

fn require_sha256(name: &str, value: &str) -> Result<(), String> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        Err(format!("{name} must be a 64-character hexadecimal SHA-256"))
    } else {
        Ok(())
    }
}

fn take_value(args: &mut impl Iterator<Item = String>, option: &str) -> Result<String, String> {
    args.next()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{option} requires a non-empty value"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn evaluator() -> EvaluatorDocument {
        EvaluatorDocument {
            schema_version: 2,
            evaluator: EvaluatorIdentity {
                id: "rust-onnx".to_owned(),
                implementation: "rust".to_owned(),
                backend: "onnxruntime".to_owned(),
            },
            capabilities: EvaluatorCapabilities {
                supported_decoders: vec!["ctc".to_owned()],
                supported_providers: vec!["cpu".to_owned()],
                supported_artifact_contracts: vec!["ctc-single-graph-v1".to_owned()],
            },
            decoder_features: BTreeMap::from([(
                "ctc".to_owned(),
                BTreeMap::from([("timestamps".to_owned(), false)]),
            )]),
        }
    }

    #[test]
    fn rejects_unsupported_decoder() {
        let error = evaluator().validate("rust-onnx", "tdt", Some("cpu")).unwrap_err();
        assert!(error.contains("evaluator capability mismatch"));
    }

    #[test]
    fn rejects_unsupported_required_feature() {
        let candidate = CandidateContract {
            schema_version: 1,
            candidate_root: "/candidate".to_owned(),
            candidate_id: "candidate-000001".to_owned(),
            profile_set: "ctc-v1".to_owned(),
            variant: "ctc".to_owned(),
            profile: "ctc-v1".to_owned(),
            decoder: "ctc".to_owned(),
            artifact_contract: "ctc-single-graph-v1".to_owned(),
            catalog: CandidateCatalog {
                id: "catalog-v1".to_owned(),
                sha256: "a".repeat(64),
            },
            bundle_sha256: "b".repeat(64),
            artifacts: BTreeMap::from([(
                "primary".to_owned(),
                CandidateArtifact {
                    path: "model.onnx".to_owned(),
                    sha256: "c".repeat(64),
                    size_bytes: 1,
                },
            )]),
            tokenizer: Some(CandidateTokenizer {
                kind: "vocabulary".to_owned(),
                path: "vocab.json".to_owned(),
            }),
            features: BTreeMap::from([("timestamps".to_owned(), true)]),
            runtime_contract: CandidateRuntimeContract {
                decoder: "ctc".to_owned(),
                input_kind: "canonical_waveform".to_owned(),
                io: Value::Object(Default::default()),
                decoder_config: Value::Object(Default::default()),
            },
        };
        let error = evaluator()
            .validate_candidate("ctc", &candidate)
            .unwrap_err();
        assert!(error.contains("unsupported evaluator feature"));
    }
}
