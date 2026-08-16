use std::env;
use std::path::PathBuf;

use asr_capsule::{CapsuleError, CapsuleSummary, read_capsule_summary};

fn usage() -> &'static str {
    "usage:\n  asr-capsule validate <run.parquet> [--expected-run-id <run-id>] [--json]\n  asr-capsule summary <run.parquet> [--json]"
}

fn summary_json(summary: &CapsuleSummary) -> serde_json::Value {
    serde_json::json!({
        "run_id": &summary.run_id,
        "row_count": summary.row_count,
        "sample_count": summary.sample_count,
        "diagnostic_count": summary.diagnostic_count,
        "artifact_count": summary.artifact_ids.len(),
        "artifact_ids": &summary.artifact_ids,
        "metrics": &summary.metrics,
    })
}

fn print_summary(summary: &CapsuleSummary, json: bool) -> Result<(), CapsuleError> {
    if json {
        println!("{}", serde_json::to_string(&summary_json(summary))?);
    } else {
        println!("run_id={}", summary.run_id);
        println!("row_count={}", summary.row_count);
        println!("sample_count={}", summary.sample_count);
        println!("diagnostic_count={}", summary.diagnostic_count);
        println!("artifact_count={}", summary.artifact_ids.len());
    }
    Ok(())
}

fn parse_path_and_flags(
    args: impl IntoIterator<Item = String>,
    allow_expected_run_id: bool,
) -> Result<(PathBuf, Option<String>, bool), String> {
    let mut args = args.into_iter();
    let path = args
        .next()
        .map(PathBuf::from)
        .ok_or_else(|| usage().to_owned())?;
    let mut expected_run_id = None;
    let mut json = false;

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--json" => json = true,
            "--expected-run-id" if allow_expected_run_id => {
                let value = args
                    .next()
                    .ok_or_else(|| "--expected-run-id requires a value".to_owned())?;
                if value.is_empty() {
                    return Err("--expected-run-id must not be empty".to_owned());
                }
                expected_run_id = Some(value);
            }
            other => return Err(format!("unsupported argument: {other}\n{}", usage())),
        }
    }

    Ok((path, expected_run_id, json))
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(|| usage().to_owned())?;

    match command.as_str() {
        "validate" => {
            let (path, expected_run_id, json) = parse_path_and_flags(args, true)?;
            let summary = read_capsule_summary(&path).map_err(|error| error.to_string())?;
            if let Some(expected) = expected_run_id {
                if summary.run_id != expected {
                    return Err(format!(
                        "capsule run_id does not match expected run_id: capsule={:?}, expected={expected:?}",
                        summary.run_id
                    ));
                }
            }
            print_summary(&summary, json).map_err(|error| error.to_string())?;
        }
        "summary" => {
            let (path, expected_run_id, json) = parse_path_and_flags(args, false)?;
            debug_assert!(expected_run_id.is_none());
            let summary = read_capsule_summary(&path).map_err(|error| error.to_string())?;
            print_summary(&summary, json).map_err(|error| error.to_string())?;
        }
        other => return Err(format!("unsupported command: {other}\n{}", usage())),
    }

    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-capsule: {error}");
        std::process::exit(2);
    }
}
