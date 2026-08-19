use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use asr_contracts::{validate_benchmark, validate_run_context};
use chrono::{SecondsFormat, Utc};
use serde_json::{Value, json};

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-promotion: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    match args.next().as_deref() {
        Some("inspect") => inspect_command(args),
        Some("write-record") => write_record_command(args),
        _ => Err(usage().to_owned()),
    }
}

fn usage() -> &'static str {
    "usage:\n  asr-promotion inspect --run-directory <dir> --candidate-id <id> [--allow-non-full]\n  asr-promotion write-record --output <promotion.json> --candidate-id <id> --run-id <id> --model-id <id> --candidate-sha256 <sha256> --runtime-variant <variant> [--revision-bundle-sha256 <sha256>] --evaluation-id <id> --provider-id <id> --bucket <namespace/name> --model-repo <namespace/name>"
}

fn inspect_command(mut args: impl Iterator<Item = String>) -> Result<(), String> {
    let mut run_directory = None;
    let mut candidate_id = None;
    let mut allow_non_full = false;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--run-directory" => {
                run_directory = Some(PathBuf::from(take_value(&mut args, "--run-directory")?))
            }
            "--candidate-id" => candidate_id = Some(take_value(&mut args, "--candidate-id")?),
            "--allow-non-full" => allow_non_full = true,
            other => return Err(format!("unsupported argument: {other}\n{}", usage())),
        }
    }
    let run_directory = run_directory.ok_or_else(|| "--run-directory is required".to_owned())?;
    let candidate_id = candidate_id.ok_or_else(|| "--candidate-id is required".to_owned())?;
    let summary = inspect_run(&run_directory, &candidate_id, allow_non_full)?;
    println!("run_directory={}", summary.run_directory.display());
    println!("run_id={}", summary.run_id);
    println!("candidate_sha256={}", summary.candidate_sha256);
    println!("runtime_variant={}", summary.runtime_variant);
    println!("model_id={}", summary.model_id);
    println!("evaluation_id={}", summary.evaluation_id);
    println!("provider_id={}", summary.provider_id);
    println!("revision_bundle_sha256={}", summary.revision_bundle_sha256);
    println!(
        "provenance_manifest_sha256={}",
        summary.provenance_manifest_sha256
    );
    Ok(())
}

fn write_record_command(mut args: impl Iterator<Item = String>) -> Result<(), String> {
    let mut output = None;
    let mut candidate_id = None;
    let mut run_id = None;
    let mut model_id = None;
    let mut candidate_sha256 = None;
    let mut runtime_variant = None;
    let mut revision_bundle_sha256 = None;
    let mut evaluation_id = None;
    let mut provider_id = None;
    let mut bucket = None;
    let mut model_repo = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--output" => output = Some(PathBuf::from(take_value(&mut args, "--output")?)),
            "--candidate-id" => candidate_id = Some(take_value(&mut args, "--candidate-id")?),
            "--run-id" => run_id = Some(take_value(&mut args, "--run-id")?),
            "--model-id" => model_id = Some(take_value(&mut args, "--model-id")?),
            "--candidate-sha256" => {
                candidate_sha256 = Some(take_value(&mut args, "--candidate-sha256")?)
            }
            "--runtime-variant" => {
                runtime_variant = Some(take_value(&mut args, "--runtime-variant")?)
            }
            "--revision-bundle-sha256" => {
                revision_bundle_sha256 = Some(take_value(&mut args, "--revision-bundle-sha256")?)
            }
            "--evaluation-id" => evaluation_id = Some(take_value(&mut args, "--evaluation-id")?),
            "--provider-id" => provider_id = Some(take_value(&mut args, "--provider-id")?),
            "--bucket" => bucket = Some(take_value(&mut args, "--bucket")?),
            "--model-repo" => model_repo = Some(take_value(&mut args, "--model-repo")?),
            other => return Err(format!("unsupported argument: {other}\n{}", usage())),
        }
    }

    let record = PromotionRecordInput {
        candidate_id: required_option(candidate_id, "--candidate-id")?,
        run_id: required_option(run_id, "--run-id")?,
        model_id: required_option(model_id, "--model-id")?,
        candidate_sha256: required_option(candidate_sha256, "--candidate-sha256")?,
        runtime_variant: required_option(runtime_variant, "--runtime-variant")?,
        revision_bundle_sha256,
        evaluation_id: required_option(evaluation_id, "--evaluation-id")?,
        provider_id: required_option(provider_id, "--provider-id")?,
        bucket: required_option(bucket, "--bucket")?,
        model_repo: required_option(model_repo, "--model-repo")?,
    };
    let output = output.ok_or_else(|| "--output is required".to_owned())?;
    write_promotion_record(&output, &record)?;
    println!("promotion_path={}", output.display());
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PromotionSummary {
    run_directory: PathBuf,
    run_id: String,
    candidate_sha256: String,
    runtime_variant: String,
    model_id: String,
    evaluation_id: String,
    provider_id: String,
    revision_bundle_sha256: String,
    provenance_manifest_sha256: String,
}

fn inspect_run(
    run_directory: &Path,
    expected_candidate_id: &str,
    allow_non_full: bool,
) -> Result<PromotionSummary, String> {
    validate_identity("candidate ID", expected_candidate_id)?;
    let run_directory = run_directory
        .canonicalize()
        .map_err(|error| format!("{}: {error}", run_directory.display()))?;
    if !run_directory.is_dir() {
        return Err(format!(
            "run directory does not exist: {}",
            run_directory.display()
        ));
    }
    reject_line_breaks("run directory", &run_directory.to_string_lossy())?;

    let run = read_json(&run_directory.join("run-context.json"))?;
    let metrics = read_json(&run_directory.join("metrics.json"))?;
    validate_run_context(&run).map_err(|error| error.to_string())?;
    validate_benchmark(&metrics).map_err(|error| error.to_string())?;

    let run_id = required_identity(&run, "/run_id", "run-context run_id")?;
    let metrics_run_id = required_identity(&metrics, "/run_id", "metrics run_id")?;
    if run_id != metrics_run_id {
        return Err("run-context and metrics run IDs differ".to_owned());
    }

    let metrics_candidate_id = required_identity(
        &metrics,
        "/candidate/candidate_id",
        "metrics candidate.candidate_id",
    )?;
    if metrics_candidate_id != expected_candidate_id {
        return Err("metrics candidate ID mismatch".to_owned());
    }
    if metrics
        .pointer("/acceptance/passed")
        .and_then(Value::as_bool)
        != Some(true)
    {
        return Err("candidate is not accepted".to_owned());
    }

    let evaluation_id = required_identity(&run, "/evaluation_id", "run-context evaluation_id")?;
    if evaluation_id != "full" && !allow_non_full {
        return Err(format!(
            "promotion requires full evaluation, got {evaluation_id:?}"
        ));
    }

    let provenance_candidate_id = required_identity(
        &run,
        "/metadata/candidate/candidate_id",
        "run-context metadata.candidate.candidate_id",
    )?;
    if provenance_candidate_id != expected_candidate_id {
        return Err("run-context candidate ID mismatch".to_owned());
    }
    let runtime_variant = required_identity(
        &run,
        "/metadata/candidate/variant",
        "run-context metadata.candidate.variant",
    )?;
    let candidate_sha256 = required_identity(
        &run,
        "/metadata/candidate/bundle_sha256",
        "run-context metadata.candidate.bundle_sha256",
    )?;
    validate_sha256("candidate bundle SHA-256", &candidate_sha256)?;

    let metrics_candidate_sha256 = required_identity(
        &metrics,
        "/candidate/artifact_sha256",
        "metrics candidate.artifact_sha256",
    )?;
    if metrics_candidate_sha256 != candidate_sha256 {
        return Err(
            "metrics candidate identity must equal run-context candidate bundle SHA".to_owned(),
        );
    }

    let model_id = required_identity(&run, "/model_id", "run-context model_id")?;
    let provider_id = required_identity(&run, "/provider_id", "run-context provider_id")?;
    let revision_bundle_sha256 = run
        .pointer("/revisions/bundle_sha256")
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or_default()
        .to_owned();
    if !revision_bundle_sha256.is_empty() {
        validate_sha256("revision bundle SHA-256", &revision_bundle_sha256)?;
    }
    let provenance = run.pointer("/metadata/provenance").ok_or_else(|| {
        "PROVENANCE_MANIFEST_MISSING: run-context provenance is required".to_owned()
    })?;
    if provenance.pointer("/status").and_then(Value::as_str) != Some("complete")
        || provenance
            .pointer("/automation_consumption")
            .and_then(Value::as_bool)
            != Some(true)
    {
        return Err(
            "PROVENANCE_AUTOMATION_DISABLED: accepted run provenance is not enabled".to_owned(),
        );
    }
    let provenance_manifest_sha256 = required_identity(
        &run,
        "/metadata/provenance/manifest_sha256",
        "run-context metadata.provenance.manifest_sha256",
    )?;
    validate_sha256("provenance manifest SHA-256", &provenance_manifest_sha256)?;

    Ok(PromotionSummary {
        run_directory,
        run_id,
        candidate_sha256,
        runtime_variant,
        model_id,
        evaluation_id,
        provider_id,
        revision_bundle_sha256,
        provenance_manifest_sha256: provenance_manifest_sha256.to_owned(),
    })
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PromotionRecordInput {
    candidate_id: String,
    run_id: String,
    model_id: String,
    candidate_sha256: String,
    runtime_variant: String,
    revision_bundle_sha256: Option<String>,
    evaluation_id: String,
    provider_id: String,
    bucket: String,
    model_repo: String,
}

fn write_promotion_record(path: &Path, input: &PromotionRecordInput) -> Result<(), String> {
    for (name, value) in [
        ("candidate ID", input.candidate_id.as_str()),
        ("run ID", input.run_id.as_str()),
        ("model ID", input.model_id.as_str()),
        ("runtime variant", input.runtime_variant.as_str()),
        ("evaluation ID", input.evaluation_id.as_str()),
        ("provider ID", input.provider_id.as_str()),
        ("bucket", input.bucket.as_str()),
        ("model repo", input.model_repo.as_str()),
    ] {
        validate_identity(name, value)?;
    }
    validate_sha256("candidate SHA-256", &input.candidate_sha256)?;
    if let Some(value) = input.revision_bundle_sha256.as_deref() {
        validate_sha256("revision bundle SHA-256", value)?;
    }
    require_namespace_name("bucket", &input.bucket)?;
    require_namespace_name("model repo", &input.model_repo)?;

    let value = json!({
        "schema_version": 3,
        "candidate_id": input.candidate_id,
        "runtime_variant": input.runtime_variant,
        "validated_run_id": input.run_id,
        "model_id": input.model_id,
        "candidate_sha256": input.candidate_sha256.to_ascii_lowercase(),
        "candidate_identity_kind": "variant_bundle",
        "revision_bundle_sha256": input.revision_bundle_sha256.as_deref(),
        "evaluation_id": input.evaluation_id,
        "provider_id": input.provider_id,
        "promoted_at": Utc::now().to_rfc3339_opts(SecondsFormat::Micros, false),
        "source": {
            "type": "hf_bucket_candidate",
            "bucket": input.bucket,
            "candidate_path": format!("candidates/{}", input.candidate_id),
        },
        "destination": {
            "type": "hf_model_repo",
            "repo_id": input.model_repo,
        },
    });
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("{}: {error}", parent.display()))?;
    }
    let mut bytes = serde_json::to_vec_pretty(&value)
        .map_err(|error| format!("failed to encode promotion record: {error}"))?;
    bytes.push(b'\n');
    fs::write(path, bytes).map_err(|error| format!("{}: {error}", path.display()))
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    serde_json::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))
}

fn required_identity(value: &Value, pointer: &str, name: &str) -> Result<String, String> {
    let value = value
        .pointer(pointer)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{name} must be a non-empty string"))?;
    validate_identity(name, value)?;
    Ok(value.to_owned())
}

fn required_option(value: Option<String>, option: &str) -> Result<String, String> {
    value.ok_or_else(|| format!("{option} is required"))
}

fn validate_identity(name: &str, value: &str) -> Result<(), String> {
    if value.trim().is_empty() {
        return Err(format!("{name} must be a non-empty string"));
    }
    reject_line_breaks(name, value)
}

fn validate_sha256(name: &str, value: &str) -> Result<(), String> {
    if value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        Ok(())
    } else {
        Err(format!("{name} must be a 64-character SHA-256"))
    }
}

fn require_namespace_name(name: &str, value: &str) -> Result<(), String> {
    if value.starts_with('/')
        || value.ends_with('/')
        || value.contains("..")
        || value.split('/').count() != 2
        || value.split('/').any(str::is_empty)
    {
        Err(format!("{name} must use namespace/name format"))
    } else {
        Ok(())
    }
}

fn reject_line_breaks(name: &str, value: &str) -> Result<(), String> {
    if value.contains(['\n', '\r']) {
        Err(format!("{name} contains a line break"))
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

    #[test]
    fn sha256_validation_is_strict() {
        assert!(validate_sha256("sha", &"a".repeat(64)).is_ok());
        assert!(validate_sha256("sha", "abc").is_err());
    }

    #[test]
    fn namespace_name_validation_is_strict() {
        assert!(require_namespace_name("bucket", "owner/name").is_ok());
        assert!(require_namespace_name("bucket", "owner/name/extra").is_err());
        assert!(require_namespace_name("bucket", "owner/../name").is_err());
    }

    #[test]
    fn identity_rejects_line_breaks() {
        assert!(validate_identity("candidate", "bad\nid").is_err());
    }
}
