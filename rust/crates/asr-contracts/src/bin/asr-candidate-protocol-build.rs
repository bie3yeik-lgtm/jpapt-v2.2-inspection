use chrono::{SecondsFormat, Utc};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-candidate-protocol-build: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(usage)?;
    let flags = parse_flags(args.collect())?;
    match command.as_str() {
        "receipt" => build_receipt(flags),
        "ack" => build_ack(flags),
        "rejection" => build_rejection(flags),
        _ => Err(usage()),
    }
}

fn usage() -> String {
    "usage: asr-candidate-protocol-build receipt --receipt PATH --dispatch-body PATH | ack --receipt PATH --ack PATH --dispatch-body PATH | rejection --rejection PATH --dispatch-body PATH".to_owned()
}

fn parse_flags(args: Vec<String>) -> Result<BTreeMap<String, String>, String> {
    let mut result = BTreeMap::new();
    let mut iter = args.into_iter();
    while let Some(flag) = iter.next() {
        if !flag.starts_with("--") {
            return Err(format!("unexpected argument {flag:?}"));
        }
        let value = iter
            .next()
            .ok_or_else(|| format!("{flag} requires a value"))?;
        if result.insert(flag.clone(), value).is_some() {
            return Err(format!("duplicate argument {flag}"));
        }
    }
    Ok(result)
}

fn required_flag(values: &mut BTreeMap<String, String>, name: &str) -> Result<String, String> {
    values
        .remove(name)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{name} is required"))
}

fn no_flags(values: BTreeMap<String, String>) -> Result<(), String> {
    if values.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "unsupported arguments: {}",
            values.keys().cloned().collect::<Vec<_>>().join(", ")
        ))
    }
}

fn environment(name: &str) -> String {
    env::var(name).unwrap_or_default()
}

fn environment_or(name: &str, default: &str) -> String {
    env::var(name).unwrap_or_else(|_| default.to_owned())
}

fn environment_u64(name: &str, default: Option<u64>) -> Result<u64, String> {
    let text = env::var(name).ok().filter(|value| !value.is_empty());
    match (text, default) {
        (Some(value), _) => value
            .parse::<u64>()
            .ok()
            .filter(|value| *value >= 1)
            .ok_or_else(|| format!("{name} must be a positive integer")),
        (None, Some(value)) => Ok(value),
        (None, None) => Err(format!("{name} is required")),
    }
}

fn environment_bool(name: &str, default: bool) -> Result<bool, String> {
    match env::var(name).ok().as_deref() {
        None | Some("") => Ok(default),
        Some("true") => Ok(true),
        Some("false") => Ok(false),
        Some(_) => Err(format!("{name} must be true or false")),
    }
}

fn nullable(value: String) -> Value {
    if value.is_empty() {
        Value::Null
    } else {
        Value::String(value)
    }
}

fn now_rfc3339() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true)
}

fn write_json(path: &Path, value: &Value, pretty: bool) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("{}: {error}", parent.display()))?;
    }
    let mut text = if pretty {
        serde_json::to_string_pretty(value).map_err(|error| error.to_string())?
    } else {
        serde_json::to_string(value).map_err(|error| error.to_string())?
    };
    text.push('\n');
    fs::write(path, text).map_err(|error| format!("{}: {error}", path.display()))
}

fn dispatch(event_type: &str, payload: &Value) -> Value {
    json!({"event_type": event_type, "client_payload": payload})
}

fn evaluation_results() -> Vec<(&'static str, String)> {
    vec![
        ("build", environment("BUILD_RESULT")),
        ("github-linux-cpu", environment("CPU_RESULT")),
        ("github-linux-cuda", environment("CUDA_RESULT")),
        ("github-macos-coreml", environment("COREML_RESULT")),
        ("github-windows-directml", environment("DIRECTML_RESULT")),
        ("hf-jobs", environment("HF_JOBS_RESULT")),
    ]
}

fn derive_conclusion(results: &[(&str, String)], dry_run: bool) -> (String, Vec<String>) {
    let relevant = results
        .iter()
        .filter(|(_, result)| !result.is_empty() && result != "skipped" && result != "success")
        .collect::<Vec<_>>();
    let failed_jobs = relevant
        .iter()
        .map(|(name, result)| format!("{name}:{result}"))
        .collect::<Vec<_>>();
    if relevant.iter().any(|(_, result)| result == "failure") {
        return ("failure".to_owned(), failed_jobs);
    }
    if relevant.iter().any(|(_, result)| result == "cancelled") {
        return ("cancelled".to_owned(), failed_jobs);
    }
    if dry_run {
        return ("success".to_owned(), failed_jobs);
    }
    let selected = results
        .iter()
        .filter(|(name, result)| *name != "build" && !result.is_empty() && result != "skipped")
        .map(|(_, result)| result.as_str())
        .collect::<Vec<_>>();
    if selected == ["success"] {
        ("success".to_owned(), failed_jobs)
    } else if failed_jobs.is_empty() {
        (
            "failure".to_owned(),
            vec!["evaluation:missing-terminal-result".to_owned()],
        )
    } else {
        ("failure".to_owned(), failed_jobs)
    }
}

fn canonical_hf_jobs_result_uri(
    bucket: &str,
    candidate_id: &str,
    suite: &str,
    run_id: u64,
    run_attempt: u64,
) -> String {
    format!(
        "hf://buckets/{bucket}/runs/hf-jobs/{candidate_id}/{suite}-{run_id}-{run_attempt}/result.json"
    )
}

fn validate_image_binding(image_ref: &str, image_digest: &str) -> Result<(), String> {
    if image_ref.is_empty() || image_digest.is_empty() {
        return Err("selected HF Jobs image ref and digest must both be present".to_owned());
    }
    let Some((name, digest)) = image_ref.rsplit_once("@sha256:") else {
        return Err("selected HF Jobs image must be digest-pinned".to_owned());
    };
    let Some(expected_digest) = image_digest.strip_prefix("sha256:") else {
        return Err("selected HF Jobs image digest must use sha256:<64 hex>".to_owned());
    };
    if name.is_empty()
        || digest.len() != 64
        || expected_digest.len() != 64
        || !digest.chars().all(|ch| ch.is_ascii_hexdigit())
        || !expected_digest.chars().all(|ch| ch.is_ascii_hexdigit())
        || !digest.eq_ignore_ascii_case(expected_digest)
    {
        return Err("selected HF Jobs image ref/digest binding is invalid".to_owned());
    }
    Ok(())
}

fn build_receipt(mut flags: BTreeMap<String, String>) -> Result<(), String> {
    let receipt_path = PathBuf::from(required_flag(&mut flags, "--receipt")?);
    let dispatch_path = PathBuf::from(required_flag(&mut flags, "--dispatch-body")?);
    no_flags(flags)?;

    let dry_run = environment_bool("DRY_RUN", false)?;
    let results = evaluation_results();
    let (conclusion, failed_jobs) = derive_conclusion(&results, dry_run);
    let requested_candidate_id = {
        let value = environment("REQUESTED_CANDIDATE_ID");
        if value.is_empty() {
            "latest".to_owned()
        } else {
            value
        }
    };
    let resolved_candidate_id = environment("RESOLVED_CANDIDATE_ID");
    let executor = environment("EXECUTOR");
    let suite = environment("SUITE");
    if executor == "hf_jobs" && suite != "smoke" {
        return Err("HF Jobs completion receipts require suite=smoke".to_owned());
    }
    let runtime_environment = environment("ENVIRONMENT");
    let run_id = environment_u64("RUN_ID", None)?;
    let run_attempt = environment_u64("RUN_ATTEMPT", Some(1))?;

    let mut image_ref = environment("IMAGE_REF");
    let mut image_digest = environment("IMAGE_DIGEST");
    if executor == "hf_jobs" {
        let selected_ref = environment("HF_JOBS_IMAGE_REF");
        let selected_digest = environment("HF_JOBS_IMAGE_DIGEST");
        if !selected_ref.is_empty() || !selected_digest.is_empty() {
            validate_image_binding(&selected_ref, &selected_digest)?;
            image_ref = selected_ref;
            image_digest = selected_digest;
        }
    }

    let mut result_artifact = Value::Null;
    let mut result_uri = Value::Null;
    if conclusion == "success" && !dry_run && !resolved_candidate_id.is_empty() {
        if executor == "hf_jobs" {
            result_artifact = Value::String(format!(
                "candidate-package-{resolved_candidate_id}-hf-jobs-{suite}"
            ));
            let expected = canonical_hf_jobs_result_uri(
                &environment("HF_BUCKET"),
                &resolved_candidate_id,
                &suite,
                run_id,
                run_attempt,
            );
            let supplied = environment("HF_JOBS_RESULT_URI");
            if !supplied.is_empty() && supplied != expected {
                return Err(format!(
                    "HF_JOBS_RESULT_URI does not match canonical job output: expected={expected} actual={supplied}"
                ));
            }
            result_uri = Value::String(if supplied.is_empty() {
                expected
            } else {
                supplied
            });
        } else {
            result_artifact = Value::String(format!(
                "candidate-package-{resolved_candidate_id}-{runtime_environment}-{suite}"
            ));
        }
    }

    let completed_at = {
        let value = environment("COMPLETED_AT");
        if value.is_empty() {
            now_rfc3339()
        } else {
            value
        }
    };

    let mut receipt = Map::new();
    receipt.insert("schema_version".to_owned(), json!(1));
    receipt.insert("request_id".to_owned(), json!(environment("REQUEST_ID")));
    let execution_id = environment("REQUEST_EXECUTION_ID");
    if !execution_id.is_empty() {
        receipt.insert("request_execution_id".to_owned(), json!(execution_id));
    }
    receipt.insert(
        "source_repository".to_owned(),
        json!(environment("SOURCE_REPOSITORY")),
    );
    receipt.insert(
        "receipt_repository".to_owned(),
        json!(environment("RECEIPT_REPOSITORY")),
    );
    receipt.insert("conclusion".to_owned(), json!(conclusion));
    receipt.insert("dry_run".to_owned(), json!(dry_run));
    receipt.insert("suite".to_owned(), json!(suite));
    receipt.insert("executor".to_owned(), json!(executor));
    receipt.insert("environment".to_owned(), json!(runtime_environment));
    receipt.insert("provider".to_owned(), json!(environment("PROVIDER")));
    receipt.insert(
        "orchestrator_repository".to_owned(),
        json!(environment("ORCHESTRATOR_REPOSITORY")),
    );
    receipt.insert(
        "workflow_file".to_owned(),
        json!("candidate-package-evaluate-v2.yml"),
    );
    receipt.insert("run_id".to_owned(), json!(run_id));
    receipt.insert("run_attempt".to_owned(), json!(run_attempt));
    receipt.insert("run_url".to_owned(), json!(environment("RUN_URL")));
    receipt.insert("commit_sha".to_owned(), json!(environment("COMMIT_SHA")));
    receipt.insert(
        "requested_candidate_id".to_owned(),
        json!(requested_candidate_id),
    );
    receipt.insert(
        "resolved_candidate_id".to_owned(),
        nullable(resolved_candidate_id),
    );
    receipt.insert("image_ref".to_owned(), nullable(image_ref));
    receipt.insert("image_digest".to_owned(), nullable(image_digest));
    receipt.insert("result_artifact".to_owned(), result_artifact);
    receipt.insert("result_uri".to_owned(), result_uri);
    receipt.insert("failed_jobs".to_owned(), json!(failed_jobs));
    receipt.insert("completed_at".to_owned(), json!(completed_at));

    let receipt = Value::Object(receipt);
    write_json(&receipt_path, &receipt, true)?;
    write_json(
        &dispatch_path,
        &dispatch("jpapt.candidate-completed", &receipt),
        false,
    )?;
    println!(
        "{}",
        serde_json::to_string_pretty(&receipt).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn read_object(path: &Path) -> Result<Map<String, Value>, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let value: Value =
        serde_json::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))?;
    value
        .as_object()
        .cloned()
        .ok_or_else(|| format!("{} must contain a JSON object", path.display()))
}

fn canonicalize(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut keys = map.keys().collect::<Vec<_>>();
            keys.sort();
            let mut output = Map::new();
            for key in keys {
                output.insert(key.clone(), canonicalize(&map[key]));
            }
            Value::Object(output)
        }
        Value::Array(items) => Value::Array(items.iter().map(canonicalize).collect()),
        other => other.clone(),
    }
}

fn canonical_sha256(value: &Map<String, Value>) -> Result<String, String> {
    let bytes = serde_json::to_vec(&canonicalize(&Value::Object(value.clone())))
        .map_err(|error| error.to_string())?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn build_ack(mut flags: BTreeMap<String, String>) -> Result<(), String> {
    let receipt_path = PathBuf::from(required_flag(&mut flags, "--receipt")?);
    let ack_path = PathBuf::from(required_flag(&mut flags, "--ack")?);
    let dispatch_path = PathBuf::from(required_flag(&mut flags, "--dispatch-body")?);
    no_flags(flags)?;
    let receipt = read_object(&receipt_path)?;
    for field in [
        "request_id",
        "receipt_repository",
        "orchestrator_repository",
        "run_id",
        "run_attempt",
    ] {
        if !receipt.contains_key(field) {
            return Err(format!("receipt is missing {field}"));
        }
    }
    let mut ack = Map::new();
    ack.insert("schema_version".to_owned(), json!(1));
    ack.insert("request_id".to_owned(), receipt["request_id"].clone());
    if let Some(value) = receipt.get("request_execution_id") {
        ack.insert("request_execution_id".to_owned(), value.clone());
    }
    ack.insert(
        "receipt_sha256".to_owned(),
        json!(canonical_sha256(&receipt)?),
    );
    ack.insert(
        "receipt_repository".to_owned(),
        receipt["receipt_repository"].clone(),
    );
    ack.insert(
        "orchestrator_repository".to_owned(),
        receipt["orchestrator_repository"].clone(),
    );
    ack.insert("evaluation_run_id".to_owned(), receipt["run_id"].clone());
    ack.insert(
        "evaluation_run_attempt".to_owned(),
        receipt["run_attempt"].clone(),
    );
    ack.insert(
        "receiver_repository".to_owned(),
        json!(environment("RECEIVER_REPOSITORY")),
    );
    ack.insert(
        "receiver_run_id".to_owned(),
        json!(environment_u64("RECEIVER_RUN_ID", None)?),
    );
    ack.insert(
        "receiver_run_attempt".to_owned(),
        json!(environment_u64("RECEIVER_RUN_ATTEMPT", Some(1))?),
    );
    ack.insert(
        "receiver_run_url".to_owned(),
        json!(environment("RECEIVER_RUN_URL")),
    );
    let accepted_at = environment("ACCEPTED_AT");
    ack.insert(
        "accepted_at".to_owned(),
        json!(if accepted_at.is_empty() {
            now_rfc3339()
        } else {
            accepted_at
        }),
    );
    let ack = Value::Object(ack);
    write_json(&ack_path, &ack, true)?;
    write_json(
        &dispatch_path,
        &dispatch("jpapt.candidate-completion-ack", &ack),
        false,
    )?;
    println!(
        "{}",
        serde_json::to_string_pretty(&ack).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn build_rejection(mut flags: BTreeMap<String, String>) -> Result<(), String> {
    let rejection_path = PathBuf::from(required_flag(&mut flags, "--rejection")?);
    let dispatch_path = PathBuf::from(required_flag(&mut flags, "--dispatch-body")?);
    no_flags(flags)?;
    let source_repository = environment("SOURCE_REPOSITORY");
    let receipt_repository = {
        let value = environment("RECEIPT_REPOSITORY");
        if value.is_empty() {
            source_repository.clone()
        } else {
            value
        }
    };
    let request_id = {
        let value = environment("REQUEST_ID");
        if value.is_empty() {
            format!(
                "gh-{}-{}",
                environment("GITHUB_RUN_ID"),
                environment_or("GITHUB_RUN_ATTEMPT", "1")
            )
        } else {
            value
        }
    };
    let rejected_at = {
        let value = environment("REJECTED_AT");
        if value.is_empty() {
            now_rfc3339()
        } else {
            value
        }
    };
    let mut rejection = Map::new();
    rejection.insert("schema_version".to_owned(), json!(1));
    rejection.insert("request_id".to_owned(), json!(request_id));
    let execution_id = environment("REQUEST_EXECUTION_ID");
    if !execution_id.is_empty() {
        rejection.insert("request_execution_id".to_owned(), json!(execution_id));
    }
    rejection.insert("source_repository".to_owned(), json!(source_repository));
    rejection.insert("receipt_repository".to_owned(), json!(receipt_repository));
    rejection.insert(
        "orchestrator_repository".to_owned(),
        json!(environment("ORCHESTRATOR_REPOSITORY")),
    );
    rejection.insert(
        "reason_code".to_owned(),
        json!("REQUEST_NORMALIZATION_OR_RESOLUTION_FAILED"),
    );
    rejection.insert(
        "gateway_run_id".to_owned(),
        json!(environment_u64("GATEWAY_RUN_ID", None)?),
    );
    rejection.insert(
        "gateway_run_attempt".to_owned(),
        json!(environment_u64("GATEWAY_RUN_ATTEMPT", Some(1))?),
    );
    rejection.insert(
        "gateway_run_url".to_owned(),
        json!(environment("GATEWAY_RUN_URL")),
    );
    rejection.insert("rejected_at".to_owned(), json!(rejected_at));
    let rejection = Value::Object(rejection);
    write_json(&rejection_path, &rejection, true)?;
    write_json(
        &dispatch_path,
        &dispatch("jpapt.candidate-rejected", &rejection),
        false,
    )?;
    println!(
        "{}",
        serde_json::to_string_pretty(&rejection).map_err(|error| error.to_string())?
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dry_run_is_success_without_terminal_evaluation() {
        let results = vec![
            ("build", "skipped".to_owned()),
            ("github-linux-cpu", "skipped".to_owned()),
            ("github-linux-cuda", "skipped".to_owned()),
            ("github-macos-coreml", "skipped".to_owned()),
            ("github-windows-directml", "skipped".to_owned()),
            ("hf-jobs", "skipped".to_owned()),
        ];
        assert_eq!(
            derive_conclusion(&results, true),
            ("success".to_owned(), vec![])
        );
    }

    #[test]
    fn missing_terminal_result_fails_non_dry_run() {
        let results = vec![
            ("build", "success".to_owned()),
            ("github-linux-cpu", "skipped".to_owned()),
            ("github-linux-cuda", "skipped".to_owned()),
            ("github-macos-coreml", "skipped".to_owned()),
            ("github-windows-directml", "skipped".to_owned()),
            ("hf-jobs", "skipped".to_owned()),
        ];
        assert_eq!(
            derive_conclusion(&results, false),
            (
                "failure".to_owned(),
                vec!["evaluation:missing-terminal-result".to_owned()]
            )
        );
    }

    #[test]
    fn hf_jobs_result_uri_uses_smoke_layout() {
        assert_eq!(
            canonical_hf_jobs_result_uri("owner/bucket", "candidate-000123", "smoke", 9001, 2),
            "hf://buckets/owner/bucket/runs/hf-jobs/candidate-000123/smoke-9001-2/result.json"
        );
    }

    #[test]
    fn validates_selected_hf_jobs_image_binding() {
        let digest = "a".repeat(64);
        let image_ref = format!("ghcr.io/owner/package@sha256:{digest}");
        let image_digest = format!("sha256:{digest}");
        validate_image_binding(&image_ref, &image_digest).unwrap();
    }

    #[test]
    fn rejects_mismatched_selected_hf_jobs_image_binding() {
        let image_ref = format!("ghcr.io/owner/package@sha256:{}", "a".repeat(64));
        let image_digest = format!("sha256:{}", "b".repeat(64));
        let error = validate_image_binding(&image_ref, &image_digest).unwrap_err();
        assert!(error.contains("binding"));
    }
}
