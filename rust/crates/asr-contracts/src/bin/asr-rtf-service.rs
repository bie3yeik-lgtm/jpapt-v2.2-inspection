use std::{env, fs, path::PathBuf};

use asr_contracts::{validate_rtf_service_metrics, validate_rtf_service_result};
use serde_json::Value;
use sha2::{Digest, Sha256};

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-rtf-service: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    if args.next().as_deref() != Some("validate") {
        return Err("usage: asr-rtf-service validate <service-result.json>".into());
    }
    let path = PathBuf::from(
        args.next()
            .ok_or_else(|| "usage: asr-rtf-service validate <service-result.json>".to_owned())?,
    );
    if args.next().is_some() {
        return Err("usage: asr-rtf-service validate <service-result.json>".into());
    }
    let value: Value = serde_json::from_str(
        &fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))?,
    )
    .map_err(|error| format!("{}: {error}", path.display()))?;
    validate_rtf_service_result(&value).map_err(|error| error.to_string())?;
    if let (Some(metrics_path), Some(expected_sha256)) = (
        value.get("metrics_path").and_then(Value::as_str),
        value.get("metrics_sha256").and_then(Value::as_str),
    ) {
        let bytes = fs::read(metrics_path).map_err(|error| format!("{}: {error}", metrics_path))?;
        let actual_sha256 = format!("{:x}", Sha256::digest(&bytes));
        if actual_sha256 != expected_sha256.to_ascii_lowercase() {
            return Err(format!(
                "metrics SHA-256 mismatch: expected={expected_sha256} actual={actual_sha256}"
            ));
        }
        let metrics: Value =
            serde_json::from_slice(&bytes).map_err(|error| format!("{}: {error}", metrics_path))?;
        validate_rtf_service_metrics(&metrics).map_err(|error| error.to_string())?;
    } else if value.get("metrics_path").and_then(Value::as_str).is_some()
        || value
            .get("metrics_sha256")
            .and_then(Value::as_str)
            .is_some()
    {
        return Err("metrics_path and metrics_sha256 must be provided together".to_owned());
    }
    println!("service_result_path={}", path.display());
    println!("service_result_status={}", value["status"]);
    Ok(())
}
