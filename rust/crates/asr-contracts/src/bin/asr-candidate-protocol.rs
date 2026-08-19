#[path = "shared/image_identity.rs"]
mod image_identity;

use chrono::DateTime;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;

const RECEIPT_REQUIRED: &[&str] = &[
    "schema_version",
    "request_id",
    "source_repository",
    "receipt_repository",
    "conclusion",
    "dry_run",
    "suite",
    "executor",
    "environment",
    "provider",
    "orchestrator_repository",
    "workflow_file",
    "run_id",
    "run_attempt",
    "run_url",
    "commit_sha",
    "requested_candidate_id",
    "resolved_candidate_id",
    "image_ref",
    "image_digest",
    "result_artifact",
    "result_uri",
    "failed_jobs",
    "completed_at",
];

const ACK_REQUIRED: &[&str] = &[
    "schema_version",
    "request_id",
    "receipt_sha256",
    "receipt_repository",
    "orchestrator_repository",
    "evaluation_run_id",
    "evaluation_run_attempt",
    "receiver_repository",
    "receiver_run_id",
    "receiver_run_attempt",
    "receiver_run_url",
    "accepted_at",
];

const REJECTION_REQUIRED: &[&str] = &[
    "schema_version",
    "request_id",
    "source_repository",
    "receipt_repository",
    "orchestrator_repository",
    "reason_code",
    "gateway_run_id",
    "gateway_run_attempt",
    "gateway_run_url",
    "rejected_at",
];

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-candidate-protocol: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    match args.next().as_deref() {
        Some("receipt-validate") => {
            let path = next_value(&mut args, "receipt-validate requires PATH")?;
            no_more(args)?;
            let value = read_object(&path)?;
            validate_receipt(&value)?;
            print_pretty(&value)
        }
        Some("receipt-sha") => {
            let path = next_value(&mut args, "receipt-sha requires PATH")?;
            no_more(args)?;
            let value = read_object(&path)?;
            validate_receipt(&value)?;
            println!("{}", canonical_sha256(&value)?);
            Ok(())
        }
        Some("ack-validate") => {
            let path = next_value(&mut args, "ack-validate requires PATH")?;
            no_more(args)?;
            let value = read_object(&path)?;
            validate_ack(&value)?;
            print_pretty(&value)
        }
        Some("rejection-validate") => {
            let path = next_value(&mut args, "rejection-validate requires PATH")?;
            no_more(args)?;
            let value = read_object(&path)?;
            validate_rejection(&value)?;
            print_pretty(&value)
        }
        Some("receiver-binding") => receiver_binding(args.collect()),
        Some("ack-binding") => ack_binding(args.collect()),
        _ => Err(usage()),
    }
}

fn usage() -> String {
    "usage: asr-candidate-protocol receipt-validate PATH | receipt-sha PATH | ack-validate PATH | rejection-validate PATH | receiver-binding --kind receipt|rejection --input PATH --receiver owner/name [--allowed CSV] | ack-binding --receipt PATH --ack PATH --orchestrator owner/name".to_owned()
}

fn next_value(args: &mut impl Iterator<Item = String>, message: &str) -> Result<String, String> {
    args.next().ok_or_else(|| message.to_owned())
}

fn no_more(mut args: impl Iterator<Item = String>) -> Result<(), String> {
    if let Some(extra) = args.next() {
        Err(format!("unexpected argument {extra:?}"))
    } else {
        Ok(())
    }
}

fn parse_flags(args: Vec<String>) -> Result<BTreeMap<String, String>, String> {
    let mut values = BTreeMap::new();
    let mut iter = args.into_iter();
    while let Some(flag) = iter.next() {
        if !flag.starts_with("--") {
            return Err(format!("unexpected argument {flag:?}"));
        }
        let value = iter
            .next()
            .ok_or_else(|| format!("{flag} requires a value"))?;
        if values.insert(flag.clone(), value).is_some() {
            return Err(format!("duplicate argument {flag}"));
        }
    }
    Ok(values)
}

fn take_required(values: &mut BTreeMap<String, String>, key: &str) -> Result<String, String> {
    values
        .remove(key)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{key} is required"))
}

fn reject_unknown(values: BTreeMap<String, String>) -> Result<(), String> {
    if values.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "unsupported arguments: {}",
            values.keys().cloned().collect::<Vec<_>>().join(", ")
        ))
    }
}

fn receiver_binding(args: Vec<String>) -> Result<(), String> {
    let mut values = parse_flags(args)?;
    let kind = take_required(&mut values, "--kind")?;
    let path = take_required(&mut values, "--input")?;
    let receiver = take_required(&mut values, "--receiver")?;
    let allowed = values.remove("--allowed").unwrap_or_default();
    reject_unknown(values)?;
    validate_repository(&receiver, "receiver repository")?;
    let value = read_object(&path)?;
    match kind.as_str() {
        "receipt" => validate_receipt(&value)?,
        "rejection" => validate_rejection(&value)?,
        _ => return Err("--kind must be receipt or rejection".to_owned()),
    }
    validate_receiver_binding(&value, &receiver, &allowed, &kind)
}

fn ack_binding(args: Vec<String>) -> Result<(), String> {
    let mut values = parse_flags(args)?;
    let receipt_path = take_required(&mut values, "--receipt")?;
    let ack_path = take_required(&mut values, "--ack")?;
    let orchestrator = take_required(&mut values, "--orchestrator")?;
    reject_unknown(values)?;
    validate_repository(&orchestrator, "orchestrator repository")?;
    let receipt = read_object(&receipt_path)?;
    let ack = read_object(&ack_path)?;
    validate_receipt(&receipt)?;
    validate_ack(&ack)?;
    validate_ack_binding(&receipt, &ack, &orchestrator)
}

fn read_object(path: &str) -> Result<Map<String, Value>, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{path}: {error}"))?;
    let value: Value = serde_json::from_str(&text).map_err(|error| format!("{path}: {error}"))?;
    value
        .as_object()
        .cloned()
        .ok_or_else(|| format!("{path} must contain a JSON object"))
}

fn print_pretty(value: &Map<String, Value>) -> Result<(), String> {
    println!(
        "{}",
        serde_json::to_string_pretty(value).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn exact_fields(
    value: &Map<String, Value>,
    required: &[&str],
    optional: &[&str],
    label: &str,
) -> Result<(), String> {
    let required = required.iter().copied().collect::<BTreeSet<_>>();
    let optional = optional.iter().copied().collect::<BTreeSet<_>>();
    let actual = value.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let missing = required.difference(&actual).copied().collect::<Vec<_>>();
    let unknown = actual
        .difference(&required)
        .filter(|field| !optional.contains(**field))
        .copied()
        .collect::<Vec<_>>();
    if missing.is_empty() && unknown.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "{label} fields mismatch: missing={missing:?}, unknown={unknown:?}"
        ))
    }
}

fn required<'a>(value: &'a Map<String, Value>, field: &str) -> Result<&'a Value, String> {
    value
        .get(field)
        .ok_or_else(|| format!("{field} is required"))
}

fn required_string<'a>(value: &'a Map<String, Value>, field: &str) -> Result<&'a str, String> {
    required(value, field)?
        .as_str()
        .filter(|text| !text.is_empty())
        .ok_or_else(|| format!("{field} must be a non-empty string"))
}

fn optional_string<'a>(
    value: &'a Map<String, Value>,
    field: &str,
) -> Result<Option<&'a str>, String> {
    match required(value, field)? {
        Value::Null => Ok(None),
        Value::String(text) if !text.is_empty() => Ok(Some(text)),
        _ => Err(format!("{field} is invalid")),
    }
}

fn positive_integer(value: &Map<String, Value>, field: &str) -> Result<u64, String> {
    required(value, field)?
        .as_u64()
        .filter(|number| *number >= 1)
        .ok_or_else(|| format!("{field} must be a positive integer"))
}

fn validate_protocol_id(value: &str, field: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > 128 {
        return Err(format!("{field} is invalid"));
    }
    if value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || ". _:-".replace(' ', "").contains(ch))
    {
        Ok(())
    } else {
        Err(format!("{field} is invalid"))
    }
}

fn validate_repository(value: &str, field: &str) -> Result<(), String> {
    let parts = value.split('/').collect::<Vec<_>>();
    if parts.len() != 2 || parts.iter().any(|part| part.is_empty()) {
        return Err(format!("{field} must use owner/name"));
    }
    if parts.iter().any(|part| matches!(*part, "." | "..")) {
        return Err(format!("{field} must not contain dot path segments"));
    }
    if value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "._-/".contains(ch))
    {
        Ok(())
    } else {
        Err(format!("{field} must use owner/name"))
    }
}

fn validate_candidate(value: &str, allow_latest: bool, field: &str) -> Result<(), String> {
    if allow_latest && value == "latest" {
        return Ok(());
    }
    if value.len() == 16
        && value.starts_with("candidate-")
        && value[10..].chars().all(|ch| ch.is_ascii_digit())
    {
        Ok(())
    } else {
        Err(format!("{field} is invalid"))
    }
}

fn validate_hex(value: &str, len: usize, prefix: &str, field: &str) -> Result<(), String> {
    let raw = value
        .strip_prefix(prefix)
        .ok_or_else(|| format!("{field} is invalid"))?;
    if raw.len() == len
        && raw
            .chars()
            .all(|ch| ch.is_ascii_hexdigit() && !ch.is_ascii_uppercase())
    {
        Ok(())
    } else {
        Err(format!("{field} is invalid"))
    }
}

fn validate_https_url(value: &str, field: &str) -> Result<(), String> {
    let invalid = || format!("{field} must be a valid ASCII HTTPS URI with a hostname");
    if !value.is_ascii()
        || value
            .chars()
            .any(|ch| ch.is_ascii_control() || ch.is_ascii_whitespace())
    {
        return Err(invalid());
    }
    let rest = value.strip_prefix("https://").ok_or_else(&invalid)?;
    let authority_end = rest
        .char_indices()
        .find(|(_, ch)| matches!(ch, '/' | '?' | '#'))
        .map(|(index, _)| index)
        .unwrap_or(rest.len());
    let authority = &rest[..authority_end];
    if authority.is_empty() || authority.contains('@') {
        return Err(invalid());
    }

    let (host, port) = match authority.rsplit_once(':') {
        Some((host, port)) if !host.contains(':') => (host, Some(port)),
        Some(_) => return Err(invalid()),
        None => (authority, None),
    };
    if host.is_empty() {
        return Err(invalid());
    }
    for label in host.split('.') {
        if label.is_empty()
            || !label
                .chars()
                .all(|ch| ch.is_ascii_alphanumeric() || ch == '-')
            || !label
                .chars()
                .next()
                .is_some_and(|ch| ch.is_ascii_alphanumeric())
            || !label
                .chars()
                .last()
                .is_some_and(|ch| ch.is_ascii_alphanumeric())
        {
            return Err(invalid());
        }
    }
    if let Some(port) = port {
        let parsed = port
            .parse::<u16>()
            .ok()
            .filter(|port| *port != 0)
            .ok_or_else(&invalid)?;
        let _ = parsed;
    }

    let suffix = &rest[authority_end..];
    let bytes = suffix.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        let byte = bytes[index];
        if byte == b'%' {
            if index + 2 >= bytes.len()
                || !bytes[index + 1].is_ascii_hexdigit()
                || !bytes[index + 2].is_ascii_hexdigit()
            {
                return Err(invalid());
            }
            index += 3;
            continue;
        }
        let ch = byte as char;
        if !(ch.is_ascii_alphanumeric() || "-._~:/?#[]@!$&'()*+,;=".contains(ch)) {
            return Err(invalid());
        }
        index += 1;
    }
    Ok(())
}

fn validate_rfc3339(value: &str, field: &str) -> Result<(), String> {
    DateTime::parse_from_rfc3339(value)
        .map(|_| ())
        .map_err(|_| format!("{field} must be a valid RFC3339 timestamp with timezone"))
}

fn validate_receipt(value: &Map<String, Value>) -> Result<(), String> {
    exact_fields(
        value,
        RECEIPT_REQUIRED,
        &["request_execution_id"],
        "receipt",
    )?;
    if required(value, "schema_version")?.as_u64() != Some(1) {
        return Err("schema_version must be 1".to_owned());
    }
    validate_protocol_id(required_string(value, "request_id")?, "request_id")?;
    if let Some(execution) = value.get("request_execution_id") {
        validate_protocol_id(
            execution
                .as_str()
                .ok_or_else(|| "request_execution_id is invalid".to_owned())?,
            "request_execution_id",
        )?;
    }
    for field in [
        "source_repository",
        "receipt_repository",
        "orchestrator_repository",
    ] {
        validate_repository(required_string(value, field)?, field)?;
    }
    if !["success", "failure", "cancelled"].contains(&required_string(value, "conclusion")?) {
        return Err("conclusion is invalid".to_owned());
    }
    let dry_run = required(value, "dry_run")?
        .as_bool()
        .ok_or_else(|| "dry_run must be boolean".to_owned())?;
    if !["smoke", "parity", "probe"].contains(&required_string(value, "suite")?) {
        return Err("suite is invalid".to_owned());
    }
    if !["github", "hf_jobs"].contains(&required_string(value, "executor")?) {
        return Err("executor is invalid".to_owned());
    }
    if ![
        "linux-cpu",
        "linux-cuda",
        "macos-coreml",
        "windows-directml",
    ]
    .contains(&required_string(value, "environment")?)
    {
        return Err("environment is invalid".to_owned());
    }
    required_string(value, "provider")?;
    if required_string(value, "workflow_file")? != "candidate-package-evaluate-v2.yml" {
        return Err("workflow_file is invalid".to_owned());
    }
    positive_integer(value, "run_id")?;
    positive_integer(value, "run_attempt")?;
    validate_https_url(required_string(value, "run_url")?, "run_url")?;
    validate_hex(required_string(value, "commit_sha")?, 40, "", "commit_sha")?;
    validate_candidate(
        required_string(value, "requested_candidate_id")?,
        true,
        "requested_candidate_id",
    )?;
    if let Some(candidate) = optional_string(value, "resolved_candidate_id")? {
        validate_candidate(candidate, false, "resolved_candidate_id")?;
    }
    for field in ["image_ref", "result_artifact", "result_uri"] {
        optional_string(value, field)?;
    }
    if let Some(digest) = optional_string(value, "image_digest")? {
        validate_hex(digest, 64, "sha256:", "image_digest")?;
    }
    if required_string(value, "conclusion")? == "success" && !dry_run {
        for field in [
            "resolved_candidate_id",
            "image_ref",
            "image_digest",
            "result_artifact",
        ] {
            if optional_string(value, field)?.is_none() {
                return Err(format!("successful evaluation receipt requires {field}"));
            }
        }
        if required_string(value, "executor")? == "hf_jobs" {
            image_identity::validate_digest_pinned_image_binding(
                optional_string(value, "image_ref")?.expect("successful receipt checked above"),
                optional_string(value, "image_digest")?.expect("successful receipt checked above"),
                "successful HF Jobs receipt image",
            )?;
        }
    }
    let failed = required(value, "failed_jobs")?
        .as_array()
        .ok_or_else(|| "failed_jobs is invalid".to_owned())?;
    let mut seen_failed_jobs = BTreeSet::new();
    for item in failed {
        let job = item
            .as_str()
            .filter(|text| !text.is_empty())
            .ok_or_else(|| "failed_jobs is invalid".to_owned())?;
        if !seen_failed_jobs.insert(job) {
            return Err("failed_jobs must contain unique values".to_owned());
        }
    }
    validate_rfc3339(required_string(value, "completed_at")?, "completed_at")
}

fn validate_ack(value: &Map<String, Value>) -> Result<(), String> {
    exact_fields(value, ACK_REQUIRED, &["request_execution_id"], "ack")?;
    if required(value, "schema_version")?.as_u64() != Some(1) {
        return Err("schema_version must be 1".to_owned());
    }
    validate_protocol_id(required_string(value, "request_id")?, "request_id")?;
    if let Some(execution) = value.get("request_execution_id") {
        validate_protocol_id(
            execution
                .as_str()
                .ok_or_else(|| "request_execution_id is invalid".to_owned())?,
            "request_execution_id",
        )?;
    }
    validate_hex(
        required_string(value, "receipt_sha256")?,
        64,
        "",
        "receipt_sha256",
    )?;
    for field in [
        "receipt_repository",
        "orchestrator_repository",
        "receiver_repository",
    ] {
        validate_repository(required_string(value, field)?, field)?;
    }
    for field in [
        "evaluation_run_id",
        "evaluation_run_attempt",
        "receiver_run_id",
        "receiver_run_attempt",
    ] {
        positive_integer(value, field)?;
    }
    validate_https_url(
        required_string(value, "receiver_run_url")?,
        "receiver_run_url",
    )?;
    validate_rfc3339(required_string(value, "accepted_at")?, "accepted_at")
}

fn validate_rejection(value: &Map<String, Value>) -> Result<(), String> {
    exact_fields(
        value,
        REJECTION_REQUIRED,
        &["request_execution_id"],
        "rejection",
    )?;
    if required(value, "schema_version")?.as_u64() != Some(1) {
        return Err("schema_version must be 1".to_owned());
    }
    validate_protocol_id(required_string(value, "request_id")?, "request_id")?;
    if let Some(execution) = value.get("request_execution_id") {
        validate_protocol_id(
            execution
                .as_str()
                .ok_or_else(|| "request_execution_id is invalid".to_owned())?,
            "request_execution_id",
        )?;
    }
    for field in [
        "source_repository",
        "receipt_repository",
        "orchestrator_repository",
    ] {
        validate_repository(required_string(value, field)?, field)?;
    }
    if required_string(value, "reason_code")? != "REQUEST_NORMALIZATION_OR_RESOLUTION_FAILED" {
        return Err("reason_code is invalid".to_owned());
    }
    positive_integer(value, "gateway_run_id")?;
    positive_integer(value, "gateway_run_attempt")?;
    validate_https_url(
        required_string(value, "gateway_run_url")?,
        "gateway_run_url",
    )?;
    validate_rfc3339(required_string(value, "rejected_at")?, "rejected_at")
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

fn validate_receiver_binding(
    value: &Map<String, Value>,
    receiver: &str,
    allowed_raw: &str,
    label: &str,
) -> Result<(), String> {
    let receipt_repository = required_string(value, "receipt_repository")?;
    if receipt_repository != receiver {
        return Err(format!(
            "{label} receipt_repository does not match receiver repository: {receipt_repository} != {receiver}"
        ));
    }
    let orchestrator = required_string(value, "orchestrator_repository")?;
    if orchestrator == receiver {
        return Ok(());
    }
    let allowed = allowed_raw
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .collect::<BTreeSet<_>>();
    if allowed.is_empty() {
        return Err(format!(
            "external {label} orchestrator is not allowed: configure JPAPT_ORCHESTRATOR_REPOSITORIES"
        ));
    }
    if !allowed.contains(orchestrator) {
        return Err(format!(
            "{label} orchestrator_repository is not allowlisted: {orchestrator}"
        ));
    }
    Ok(())
}

fn validate_ack_binding(
    receipt: &Map<String, Value>,
    ack: &Map<String, Value>,
    orchestrator: &str,
) -> Result<(), String> {
    let checks = [
        (
            "orchestrator_repository",
            Value::String(orchestrator.to_owned()),
        ),
        ("request_id", required(receipt, "request_id")?.clone()),
        (
            "receipt_repository",
            required(receipt, "receipt_repository")?.clone(),
        ),
        ("evaluation_run_id", required(receipt, "run_id")?.clone()),
        (
            "evaluation_run_attempt",
            required(receipt, "run_attempt")?.clone(),
        ),
        (
            "receiver_repository",
            required(receipt, "receipt_repository")?.clone(),
        ),
    ];
    for (field, expected) in checks {
        let actual = required(ack, field)?;
        if actual != &expected {
            return Err(format!(
                "ACK binding mismatch for {field}: {actual:?} != {expected:?}"
            ));
        }
    }
    match (
        receipt.get("request_execution_id"),
        ack.get("request_execution_id"),
    ) {
        (Some(expected), Some(actual)) if expected == actual => Ok(()),
        (Some(expected), Some(actual)) => Err(format!(
            "ACK binding mismatch for request_execution_id: {actual:?} != {expected:?}"
        )),
        (Some(_), None) => Err("ACK binding mismatch for request_execution_id: missing".to_owned()),
        (None, Some(_)) => {
            Err("ACK contains request_execution_id but legacy receipt does not".to_owned())
        }
        (None, None) => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn receipt() -> Map<String, Value> {
        json!({
            "schema_version":1,
            "request_id":"req-001",
            "request_execution_id":"eval-200-1",
            "source_repository":"owner/source",
            "receipt_repository":"owner/receiver",
            "conclusion":"success",
            "dry_run":true,
            "suite":"probe",
            "executor":"github",
            "environment":"linux-cpu",
            "provider":"CPUExecutionProvider",
            "orchestrator_repository":"owner/orchestrator",
            "workflow_file":"candidate-package-evaluate-v2.yml",
            "run_id":200,
            "run_attempt":1,
            "run_url":"https://github.com/owner/orchestrator/actions/runs/200",
            "commit_sha":"0000000000000000000000000000000000000000",
            "requested_candidate_id":"latest",
            "resolved_candidate_id":null,
            "image_ref":null,
            "image_digest":null,
            "result_artifact":null,
            "result_uri":null,
            "failed_jobs":[],
            "completed_at":"2026-08-18T10:00:00Z"
        })
        .as_object()
        .unwrap()
        .clone()
    }

    #[test]
    fn repository_identity_rejects_dot_segments_but_allows_dot_prefixed_names() {
        for value in ["./repo", "../repo", "owner/.", "owner/.."] {
            assert!(validate_repository(value, "repository").is_err(), "{value}");
        }
        validate_repository("owner/.github", "repository").unwrap();
        validate_repository(".owner/repo", "repository").unwrap();
    }

    #[test]
    fn validates_canonical_https_urls() {
        validate_https_url(
            "https://github.com/owner/repo/actions/runs/123?check=1#summary",
            "run_url",
        )
        .unwrap();
        validate_https_url("https://localhost:8443/actions/runs/123", "run_url").unwrap();
    }

    #[test]
    fn rejects_malformed_https_urls() {
        for value in [
            "http://github.com/owner/repo",
            "https://",
            "https://:443/path",
            "https://github .com/path",
            "https://github..com/path",
            "https://-github.com/path",
            "https://github.com:0/path",
            "https://user@github.com/path",
            "https://github.com/%ZZ",
            "https://github.com/path with space",
        ] {
            assert!(validate_https_url(value, "run_url").is_err(), "{value}");
        }
    }

    #[test]
    fn validates_dry_run_receipt() {
        validate_receipt(&receipt()).unwrap();
    }

    #[test]
    fn validates_successful_hf_jobs_receipt_image_binding() {
        let digest = "a".repeat(64);
        let mut value = receipt();
        value.insert("dry_run".to_owned(), json!(false));
        value.insert("suite".to_owned(), json!("smoke"));
        value.insert("executor".to_owned(), json!("hf_jobs"));
        value.insert(
            "resolved_candidate_id".to_owned(),
            json!("candidate-000123"),
        );
        value.insert(
            "image_ref".to_owned(),
            json!(format!("registry.example:5000/ns/repo:tag@sha256:{digest}")),
        );
        value.insert("image_digest".to_owned(), json!(format!("sha256:{digest}")));
        value.insert(
            "result_artifact".to_owned(),
            json!("candidate-package-candidate-000123-hf-jobs-smoke"),
        );
        value.insert(
            "result_uri".to_owned(),
            json!(
                "hf://buckets/owner/bucket/runs/hf-jobs/candidate-000123/smoke-200-1/result.json"
            ),
        );
        validate_receipt(&value).unwrap();
    }

    #[test]
    fn rejects_ambiguous_or_mismatched_successful_hf_jobs_receipt_image() {
        let digest = "a".repeat(64);
        for image_ref in [
            format!("ghcr.io//owner/repo@sha256:{digest}"),
            format!("ghcr.io/./repo@sha256:{digest}"),
            format!("ghcr.io/../repo@sha256:{digest}"),
            format!("/ghcr.io/owner/repo@sha256:{digest}"),
            format!("ghcr.io/owner/repo/@sha256:{digest}"),
            format!("ghcr.io/owner/repo@sha256:{}", "b".repeat(64)),
        ] {
            let mut value = receipt();
            value.insert("dry_run".to_owned(), json!(false));
            value.insert("suite".to_owned(), json!("smoke"));
            value.insert("executor".to_owned(), json!("hf_jobs"));
            value.insert(
                "resolved_candidate_id".to_owned(),
                json!("candidate-000123"),
            );
            value.insert("image_ref".to_owned(), json!(image_ref));
            value.insert("image_digest".to_owned(), json!(format!("sha256:{digest}")));
            value.insert(
                "result_artifact".to_owned(),
                json!("candidate-package-candidate-000123-hf-jobs-smoke"),
            );
            assert!(validate_receipt(&value).is_err());
        }
    }

    #[test]
    fn github_receipt_keeps_tag_plus_separate_digest_compatibility() {
        let mut value = receipt();
        value.insert("dry_run".to_owned(), json!(false));
        value.insert("suite".to_owned(), json!("smoke"));
        value.insert("executor".to_owned(), json!("github"));
        value.insert(
            "resolved_candidate_id".to_owned(),
            json!("candidate-000123"),
        );
        value.insert(
            "image_ref".to_owned(),
            json!("ghcr.io/owner/repo:candidate-000123-linux-cpu"),
        );
        value.insert(
            "image_digest".to_owned(),
            json!(format!("sha256:{}", "a".repeat(64))),
        );
        value.insert(
            "result_artifact".to_owned(),
            json!("candidate-package-candidate-000123-linux-cpu-smoke"),
        );
        validate_receipt(&value).unwrap();
    }

    #[test]
    fn rejects_duplicate_failed_jobs() {
        let mut value = receipt();
        value.insert(
            "failed_jobs".to_owned(),
            json!(["build:failure", "build:failure"]),
        );
        assert!(validate_receipt(&value).is_err());
    }

    #[test]
    fn canonical_hash_ignores_object_key_order() {
        let first = receipt();
        let mut reversed = Map::new();
        for (key, value) in first.iter().rev() {
            reversed.insert(key.clone(), value.clone());
        }
        assert_eq!(
            canonical_sha256(&first).unwrap(),
            canonical_sha256(&reversed).unwrap()
        );
    }

    #[test]
    fn receiver_binding_requires_allowlist_for_external_orchestrator() {
        let value = receipt();
        assert!(validate_receiver_binding(&value, "owner/receiver", "", "receipt").is_err());
        validate_receiver_binding(
            &value,
            "owner/receiver",
            "owner/other,owner/orchestrator",
            "receipt",
        )
        .unwrap();
    }

    #[test]
    fn ack_binding_requires_execution_identity_match() {
        let receipt = receipt();
        let ack = json!({
            "schema_version":1,
            "request_id":"req-001",
            "request_execution_id":"eval-200-1",
            "receipt_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "receipt_repository":"owner/receiver",
            "orchestrator_repository":"owner/orchestrator",
            "evaluation_run_id":200,
            "evaluation_run_attempt":1,
            "receiver_repository":"owner/receiver",
            "receiver_run_id":300,
            "receiver_run_attempt":1,
            "receiver_run_url":"https://github.com/owner/receiver/actions/runs/300",
            "accepted_at":"2026-08-18T10:01:00Z"
        })
        .as_object()
        .unwrap()
        .clone();
        validate_ack(&ack).unwrap();
        validate_ack_binding(&receipt, &ack, "owner/orchestrator").unwrap();
    }
}
