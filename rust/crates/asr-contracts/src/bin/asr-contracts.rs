use std::env;
use std::path::PathBuf;

use asr_contracts::{validate_benchmark, validate_run_context, validate_run_directory, validate_sample_result};
use serde_json::Value;

fn usage() -> &'static str {
    "usage:\n  asr-contracts validate-run <run-directory> [--json]\n  asr-contracts validate-run-context <run-context.json>\n  asr-contracts validate-benchmark <metrics.json>\n  asr-contracts validate-sample <result.json>"
}

fn read_json(path: &PathBuf) -> Result<Value, String> {
    let text = std::fs::read_to_string(path)
        .map_err(|error| format!("{}: {error}", path.display()))?;
    serde_json::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(|| usage().to_owned())?;
    match command.as_str() {
        "validate-run" => {
            let path = args
                .next()
                .map(PathBuf::from)
                .ok_or_else(|| usage().to_owned())?;
            let mut json = false;
            for arg in args {
                match arg.as_str() {
                    "--json" => json = true,
                    other => return Err(format!("unsupported argument: {other}\n{}", usage())),
                }
            }
            let summary = validate_run_directory(&path).map_err(|error| error.to_string())?;
            if json {
                println!(
                    "{}",
                    serde_json::to_string(&summary).map_err(|error| error.to_string())?
                );
            } else {
                println!("run_id={}", summary.run_id);
                println!("sample_count={}", summary.sample_count);
            }
        }
        "validate-run-context" | "validate-benchmark" | "validate-sample" => {
            let path = args
                .next()
                .map(PathBuf::from)
                .ok_or_else(|| usage().to_owned())?;
            if args.next().is_some() {
                return Err(usage().to_owned());
            }
            let value = read_json(&path)?;
            match command.as_str() {
                "validate-run-context" => validate_run_context(&value),
                "validate-benchmark" => validate_benchmark(&value),
                "validate-sample" => validate_sample_result(&value),
                _ => unreachable!(),
            }
            .map_err(|error| error.to_string())?;
            println!("valid={}", path.display());
        }
        other => return Err(format!("unsupported command: {other}\n{}", usage())),
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-contracts: {error}");
        std::process::exit(2);
    }
}
