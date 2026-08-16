mod error;
mod schema;

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

pub use error::{ContractError, Result};
use schema::EmbeddedSchema;

const RUN_CONTEXT_SCHEMA: &str =
    include_str!("../../../../evaluation/schemas/run-context.schema.json");
const SAMPLE_RESULT_SCHEMA: &str =
    include_str!("../../../../evaluation/schemas/result.schema.json");
const BENCHMARK_SCHEMA: &str = include_str!("../../../../evaluation/schemas/benchmark.schema.json");

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RunValidationSummary {
    pub run_id: String,
    pub sample_count: usize,
}

pub fn validate_run_context(value: &Value) -> Result<()> {
    EmbeddedSchema::parse("run-context", RUN_CONTEXT_SCHEMA)?.validate(value)?;
    reject_nulls(value, "$")?;
    validate_run_context_semantics(value)
}

pub fn validate_sample_result(value: &Value) -> Result<()> {
    EmbeddedSchema::parse("result", SAMPLE_RESULT_SCHEMA)?.validate(value)
}

pub fn validate_benchmark(value: &Value) -> Result<()> {
    EmbeddedSchema::parse("benchmark", BENCHMARK_SCHEMA)?.validate(value)
}

pub fn validate_run_directory(path: impl AsRef<Path>) -> Result<RunValidationSummary> {
    let path = path.as_ref();
    if !path.is_dir() {
        return Err(ContractError::validation(format!(
            "run directory does not exist: {}",
            path.display()
        )));
    }

    let run_context = read_json(path.join("run-context.json"))?;
    validate_run_context(&run_context)?;
    let run_id = required_string_at(&run_context, "/run_id", "run-context.run_id")?.to_owned();

    let benchmark = read_json(path.join("metrics.json"))?;
    validate_benchmark(&benchmark)?;
    let benchmark_run_id = required_string_at(&benchmark, "/run_id", "benchmark.run_id")?;
    if benchmark_run_id != run_id {
        return Err(ContractError::validation(format!(
            "run-context.json and metrics.json use different run IDs: {run_id:?} != {benchmark_run_id:?}"
        )));
    }

    let samples_path = path.join("samples.jsonl");
    let text = fs::read_to_string(&samples_path).map_err(|source| ContractError::Io {
        path: samples_path.clone(),
        source,
    })?;
    let mut sample_count = 0usize;
    let mut sample_ids = BTreeSet::new();
    for (index, raw_line) in text.lines().enumerate() {
        let line = raw_line.trim();
        if line.is_empty() {
            continue;
        }
        let value: Value = serde_json::from_str(line).map_err(|source| ContractError::Json {
            path: samples_path.clone(),
            source,
        })?;
        validate_sample_result(&value).map_err(|error| {
            ContractError::validation(format!("samples.jsonl line {}: {error}", index + 1))
        })?;
        let sample_run_id = required_string_at(&value, "/run_id", "sample.run_id")?;
        if sample_run_id != run_id {
            return Err(ContractError::validation(format!(
                "samples.jsonl line {} run_id does not match run-context: {:?} != {:?}",
                index + 1,
                sample_run_id,
                run_id
            )));
        }
        let sample_id = required_string_at(&value, "/sample/id", "sample.id")?;
        if !sample_ids.insert(sample_id.to_owned()) {
            return Err(ContractError::validation(format!(
                "samples.jsonl contains duplicate sample id {sample_id:?}"
            )));
        }
        sample_count += 1;
    }

    if sample_count == 0 {
        return Err(ContractError::validation(
            "samples.jsonl contains no sample results",
        ));
    }

    Ok(RunValidationSummary {
        run_id,
        sample_count,
    })
}

fn read_json(path: PathBuf) -> Result<Value> {
    let text = fs::read_to_string(&path).map_err(|source| ContractError::Io {
        path: path.clone(),
        source,
    })?;
    serde_json::from_str(&text).map_err(|source| ContractError::Json { path, source })
}

fn validate_run_context_semantics(value: &Value) -> Result<()> {
    let provider_id = required_string_at(value, "/provider_id", "provider_id")?;
    let runtime_provider =
        required_string_at(value, "/runtime/provider_id", "runtime.provider_id")?;
    if provider_id != runtime_provider {
        return Err(ContractError::validation(
            "runtime.provider_id must equal provider_id",
        ));
    }

    let candidate = value
        .pointer("/metadata/candidate")
        .ok_or_else(|| ContractError::validation("metadata.candidate is required"))?;
    validate_generated_candidate(candidate)?;

    let artifact_candidate =
        required_string_at(value, "/artifact/candidate_id", "artifact.candidate_id")?;
    let candidate_id = required_string_at(
        candidate,
        "/candidate_id",
        "metadata.candidate.candidate_id",
    )?;
    if artifact_candidate != candidate_id {
        return Err(ContractError::validation(
            "artifact.candidate_id must equal metadata.candidate.candidate_id",
        ));
    }

    let profile_set = required_string_at(
        value,
        "/revisions/runtime/profile_set",
        "revisions.runtime.profile_set",
    )?;
    let candidate_profile_set =
        required_string_at(candidate, "/profile_set", "metadata.candidate.profile_set")?;
    if profile_set != candidate_profile_set {
        return Err(ContractError::validation(
            "metadata.candidate.profile_set must equal revisions.runtime.profile_set",
        ));
    }

    for field in ["id", "sha256"] {
        let revision_pointer = format!("/revisions/runtime/catalog/{field}");
        let candidate_pointer = format!("/catalog/{field}");
        let revision_value = required_string_at(
            value,
            &revision_pointer,
            &format!("revisions.runtime.catalog.{field}"),
        )?;
        let candidate_value = required_string_at(
            candidate,
            &candidate_pointer,
            &format!("metadata.candidate.catalog.{field}"),
        )?;
        if revision_value != candidate_value {
            return Err(ContractError::validation(
                "metadata.candidate.catalog must equal revisions.runtime.catalog",
            ));
        }
    }

    Ok(())
}

fn validate_generated_candidate(value: &Value) -> Result<()> {
    reject_nulls(value, "$.metadata.candidate")?;
    let raw = object(value, "metadata.candidate")?;
    exact_fields(
        raw,
        "metadata.candidate",
        &[
            "schema_version",
            "candidate_root",
            "candidate_id",
            "profile_set",
            "variant",
            "profile",
            "decoder",
            "artifact_contract",
            "catalog",
            "bundle_sha256",
            "artifacts",
            "features",
            "runtime_contract",
        ],
        &["tokenizer"],
    )?;

    let schema_version = raw
        .get("schema_version")
        .and_then(Value::as_u64)
        .ok_or_else(|| {
            ContractError::validation("metadata.candidate.schema_version must be an integer")
        })?;
    if schema_version != 1 {
        return Err(ContractError::validation(
            "generated candidate schema_version must equal 1",
        ));
    }

    for field in [
        "candidate_root",
        "candidate_id",
        "profile_set",
        "variant",
        "profile",
        "artifact_contract",
    ] {
        required_nonempty(raw, field, "metadata.candidate")?;
    }
    let decoder = required_nonempty(raw, "decoder", "metadata.candidate")?;
    require_one_of(
        "metadata.candidate.decoder",
        decoder,
        &["ctc", "tdt", "whisper_autoregressive"],
    )?;
    require_sha256(
        "metadata.candidate.bundle_sha256",
        required_nonempty(raw, "bundle_sha256", "metadata.candidate")?,
    )?;

    let catalog = object(
        raw.get("catalog").expect("required field checked"),
        "metadata.candidate.catalog",
    )?;
    exact_fields(
        catalog,
        "metadata.candidate.catalog",
        &["id", "sha256"],
        &[],
    )?;
    required_nonempty(catalog, "id", "metadata.candidate.catalog")?;
    require_sha256(
        "metadata.candidate.catalog.sha256",
        required_nonempty(catalog, "sha256", "metadata.candidate.catalog")?,
    )?;

    let artifacts = object(
        raw.get("artifacts").expect("required field checked"),
        "metadata.candidate.artifacts",
    )?;
    if artifacts.is_empty() {
        return Err(ContractError::validation(
            "metadata.candidate.artifacts must not be empty",
        ));
    }
    for (role, artifact) in artifacts {
        if role.trim().is_empty() {
            return Err(ContractError::validation(
                "metadata.candidate artifact roles must be non-empty strings",
            ));
        }
        let name = format!("metadata.candidate.artifacts.{role}");
        let artifact = object(artifact, &name)?;
        exact_fields(artifact, &name, &["path", "sha256", "size_bytes"], &[])?;
        required_nonempty(artifact, "path", &name)?;
        require_sha256(
            &format!("{name}.sha256"),
            required_nonempty(artifact, "sha256", &name)?,
        )?;
        let size = artifact
            .get("size_bytes")
            .and_then(Value::as_u64)
            .ok_or_else(|| {
                ContractError::validation(format!("{name}.size_bytes must be a positive integer"))
            })?;
        if size == 0 {
            return Err(ContractError::validation(format!(
                "{name}.size_bytes must be a positive integer"
            )));
        }
    }

    if let Some(tokenizer) = raw.get("tokenizer") {
        let tokenizer = object(tokenizer, "metadata.candidate.tokenizer")?;
        exact_fields(
            tokenizer,
            "metadata.candidate.tokenizer",
            &["kind", "path"],
            &[],
        )?;
        required_nonempty(tokenizer, "kind", "metadata.candidate.tokenizer")?;
        required_nonempty(tokenizer, "path", "metadata.candidate.tokenizer")?;
    }

    let features = object(
        raw.get("features").expect("required field checked"),
        "metadata.candidate.features",
    )?;
    for (name, feature) in features {
        if name.trim().is_empty() || !feature.is_boolean() {
            return Err(ContractError::validation(format!(
                "metadata.candidate.features.{name} must have a non-empty name and boolean value"
            )));
        }
    }

    let runtime = object(
        raw.get("runtime_contract").expect("required field checked"),
        "metadata.candidate.runtime_contract",
    )?;
    exact_fields(
        runtime,
        "metadata.candidate.runtime_contract",
        &["decoder", "input_kind", "io", "decoder_config"],
        &[],
    )?;
    let runtime_decoder =
        required_nonempty(runtime, "decoder", "metadata.candidate.runtime_contract")?;
    require_one_of(
        "metadata.candidate.runtime_contract.decoder",
        runtime_decoder,
        &["ctc", "tdt", "whisper_autoregressive"],
    )?;
    if decoder != runtime_decoder {
        return Err(ContractError::validation(
            "candidate.decoder must equal candidate.runtime_contract.decoder",
        ));
    }
    require_one_of(
        "metadata.candidate.runtime_contract.input_kind",
        required_nonempty(runtime, "input_kind", "metadata.candidate.runtime_contract")?,
        &["canonical_waveform", "features"],
    )?;
    object(
        runtime.get("io").expect("required field checked"),
        "metadata.candidate.runtime_contract.io",
    )?;
    object(
        runtime
            .get("decoder_config")
            .expect("required field checked"),
        "metadata.candidate.runtime_contract.decoder_config",
    )?;

    Ok(())
}

fn reject_nulls(value: &Value, path: &str) -> Result<()> {
    match value {
        Value::Null => Err(ContractError::validation(format!(
            "contract must not contain null: {path}"
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

fn object<'a>(value: &'a Value, name: &str) -> Result<&'a Map<String, Value>> {
    value
        .as_object()
        .ok_or_else(|| ContractError::validation(format!("{name} must be an object")))
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
                "{name} contains unknown field {key:?}"
            )));
        }
    }
    Ok(())
}

fn required_nonempty<'a>(value: &'a Map<String, Value>, key: &str, name: &str) -> Result<&'a str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| {
            ContractError::validation(format!("{name}.{key} must be a non-empty string"))
        })
}

fn required_string_at<'a>(value: &'a Value, pointer: &str, name: &str) -> Result<&'a str> {
    value
        .pointer(pointer)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| ContractError::validation(format!("{name} must be a non-empty string")))
}

fn require_one_of(name: &str, value: &str, allowed: &[&str]) -> Result<()> {
    if !allowed.contains(&value) {
        return Err(ContractError::validation(format!(
            "{name} has unsupported value {value:?}; expected one of {}",
            allowed.join(", ")
        )));
    }
    Ok(())
}

fn require_sha256(name: &str, value: &str) -> Result<()> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(ContractError::validation(format!(
            "{name} must be a 64-character SHA-256"
        )));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_candidate() -> Value {
        serde_json::json!({
            "schema_version":1,
            "candidate_root":"candidate",
            "candidate_id":"candidate-1",
            "profile_set":"profile-set",
            "variant":"ctc",
            "profile":"cpu",
            "decoder":"ctc",
            "artifact_contract":"contract",
            "catalog":{"id":"catalog","sha256":"a".repeat(64)},
            "bundle_sha256":"b".repeat(64),
            "artifacts":{"primary":{"path":"model.onnx","sha256":"c".repeat(64),"size_bytes":1}},
            "features":{},
            "runtime_contract":{"decoder":"ctc","input_kind":"canonical_waveform","io":{},"decoder_config":{}}
        })
    }

    #[test]
    fn generated_candidate_semantics_accept_valid_shape() {
        validate_generated_candidate(&valid_candidate()).unwrap();
    }

    #[test]
    fn generated_candidate_rejects_decoder_mismatch() {
        let mut value = valid_candidate();
        value["runtime_contract"]["decoder"] = Value::String("tdt".into());
        assert!(validate_generated_candidate(&value).is_err());
    }

    #[test]
    fn sample_schema_rejects_unknown_top_level_field() {
        let value = serde_json::json!({"schema_version":1,"extra":true});
        assert!(validate_sample_result(&value).is_err());
    }
}
