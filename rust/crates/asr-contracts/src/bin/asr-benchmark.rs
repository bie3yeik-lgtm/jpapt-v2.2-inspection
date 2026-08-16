use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use asr_contracts::validate_benchmark;
use serde_json::Value;

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-benchmark: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let path = args
        .next()
        .map(PathBuf::from)
        .ok_or_else(|| "usage: asr-benchmark <metrics.json>".to_owned())?;
    if args.next().is_some() {
        return Err("usage: asr-benchmark <metrics.json>".to_owned());
    }

    let summary = inspect_benchmark(&path)?;
    println!("metrics_path={}", summary.metrics_path.display());
    println!("run_id={}", summary.run_id);
    println!("candidate_id={}", summary.candidate_id);
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct BenchmarkSummary {
    metrics_path: PathBuf,
    run_id: String,
    candidate_id: String,
}

fn inspect_benchmark(path: &Path) -> Result<BenchmarkSummary, String> {
    let metrics_path = path
        .canonicalize()
        .map_err(|error| format!("{}: {error}", path.display()))?;
    let text = fs::read_to_string(&metrics_path)
        .map_err(|error| format!("{}: {error}", metrics_path.display()))?;
    let value: Value = serde_json::from_str(&text)
        .map_err(|error| format!("{}: {error}", metrics_path.display()))?;
    validate_benchmark(&value).map_err(|error| error.to_string())?;

    let run_id = required_identity(&value, "/run_id", "metrics.json run_id")?;
    let candidate_id = required_identity(
        &value,
        "/candidate/candidate_id",
        "metrics.json candidate.candidate_id",
    )?;
    let rendered_path = metrics_path.to_string_lossy();
    reject_line_breaks("metrics path", &rendered_path)?;

    Ok(BenchmarkSummary {
        metrics_path,
        run_id,
        candidate_id,
    })
}

fn required_identity(value: &Value, pointer: &str, name: &str) -> Result<String, String> {
    let value = value
        .pointer(pointer)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{name} must be a non-empty string"))?;
    reject_line_breaks(name, value)?;
    Ok(value.to_owned())
}

fn reject_line_breaks(name: &str, value: &str) -> Result<(), String> {
    if value.contains(['\n', '\r']) {
        Err(format!("{name} contains a line break"))
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identity_rejects_line_breaks() {
        let value = serde_json::json!({"run_id": "bad\nid"});
        assert!(required_identity(&value, "/run_id", "run_id").is_err());
    }
}
