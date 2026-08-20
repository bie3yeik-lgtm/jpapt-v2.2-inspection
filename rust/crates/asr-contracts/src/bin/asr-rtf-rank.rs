use std::cmp::Ordering;
use std::env;
use std::fs;
use std::path::PathBuf;

use asr_contracts::validate_rtf_benchmark_record;
use serde_json::Value;

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-rtf-rank: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let output = PathBuf::from(args.next().ok_or_else(|| "usage: asr-rtf-rank <output.json> <record.json>...".to_owned())?);
    let inputs: Vec<PathBuf> = args.map(PathBuf::from).collect();
    if inputs.is_empty() {
        return Err("at least one record path is required".to_owned());
    }
    let mut records = Vec::new();
    for path in inputs {
        let text = fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))?;
        let value: Value = serde_json::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))?;
        validate_rtf_benchmark_record(&value).map_err(|error| format!("{}: {error}", path.display()))?;
        if value["status"] == "completed"
            && value["provider_execution_proof"].as_bool() == Some(true)
            && value["cost_per_audio_hour"].as_f64().is_some()
            && value["cer"].as_f64().is_some()
        {
            records.push(value);
        }
    }
    records.sort_by(|left, right| {
        compare_number(left, right, "cost_per_audio_hour")
            .then_with(|| compare_number(left, right, "cer"))
            .then_with(|| compare_number(left, right, "rtf"))
            .then_with(|| left["service_id"].as_str().cmp(&right["service_id"].as_str()))
            .then_with(|| left["gpu"].as_str().cmp(&right["gpu"].as_str()))
            .then_with(|| left["batch_size"].as_u64().cmp(&right["batch_size"].as_u64()))
            .then_with(|| left["run_id"].as_str().cmp(&right["run_id"].as_str()))
    });
    let rendered = serde_json::to_string_pretty(&serde_json::json!({"schema_version": 1, "records": records}))
        .map_err(|error| error.to_string())?;
    fs::write(&output, format!("{rendered}\n")).map_err(|error| format!("{}: {error}", output.display()))?;
    Ok(())
}

fn compare_number(left: &Value, right: &Value, key: &str) -> Ordering {
    left[key].as_f64().partial_cmp(&right[key].as_f64()).unwrap_or(Ordering::Equal)
}
