use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{Map, Value, json};

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-provider-readiness: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut provider = None;
    let mut root = None;
    let mut step_outcome = None;
    let mut exit_code = String::new();

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--provider" => provider = Some(take_value(&mut args, "--provider")?),
            "--root" => root = Some(PathBuf::from(take_value(&mut args, "--root")?)),
            "--step-outcome" => {
                step_outcome = Some(take_value(&mut args, "--step-outcome")?)
            }
            "--exit-code" => exit_code = take_value(&mut args, "--exit-code")?,
            other => return Err(format!("unsupported argument {other:?}\n{}", usage())),
        }
    }

    let provider = provider.ok_or_else(|| "--provider is required".to_owned())?;
    let root = root.ok_or_else(|| "--root is required".to_owned())?;
    let step_outcome = step_outcome.ok_or_else(|| "--step-outcome is required".to_owned())?;
    fs::create_dir_all(&root).map_err(|error| format!("{}: {error}", root.display()))?;

    let metrics = read_optional_json(&root.join("results/metrics.json"))?;
    let (result, output_name, strict_classification) = match provider.as_str() {
        "coreml" => {
            let stderr = read_optional_text(&root.join("coreml.stderr.txt"))?;
            (
                classify_coreml(metrics.as_ref(), &stderr, &step_outcome, &exit_code),
                "coreml-readiness.json",
                true,
            )
        }
        "directml" => (
            classify_directml(metrics.as_ref(), &step_outcome, &exit_code),
            "directml-readiness.json",
            false,
        ),
        other => return Err(format!("unsupported provider {other:?}; expected coreml or directml")),
    };

    let output = root.join(output_name);
    let mut bytes = serde_json::to_vec_pretty(&result).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(&output, bytes).map_err(|error| format!("{}: {error}", output.display()))?;
    println!(
        "{}",
        serde_json::to_string_pretty(&result).map_err(|error| error.to_string())?
    );

    if strict_classification {
        let classification = result
            .get("classification")
            .and_then(Value::as_str)
            .unwrap_or("unknown_failure");
        if !matches!(
            classification,
            "strict_execution_proven" | "strict_rejected_cpu_assigned_nodes"
        ) {
            return Err("CoreML readiness failed for an unclassified reason".to_owned());
        }
    }
    Ok(())
}

fn usage() -> &'static str {
    "usage: asr-provider-readiness --provider <coreml|directml> --root <probe-dir> --step-outcome <outcome> [--exit-code <code>]"
}

fn take_value(args: &mut impl Iterator<Item = String>, option: &str) -> Result<String, String> {
    args.next()
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| format!("{option} requires a non-empty value"))
}

fn read_optional_json(path: &Path) -> Result<Option<Value>, String> {
    if !path.is_file() {
        return Ok(None);
    }
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let value = serde_json::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))?;
    Ok(Some(value))
}

fn read_optional_text(path: &Path) -> Result<String, String> {
    if !path.is_file() {
        return Ok(String::new());
    }
    fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))
}

fn metrics_provider(metrics: Option<&Value>) -> Option<&Map<String, Value>> {
    metrics?.get("provider")?.as_object()
}

fn classify_coreml(
    metrics: Option<&Value>,
    stderr: &str,
    step_outcome: &str,
    exit_code: &str,
) -> Value {
    let provider = metrics_provider(metrics);
    let execution_proven = provider
        .and_then(|value| value.get("execution_proven"))
        .and_then(Value::as_bool)
        == Some(true);
    let fallback_detected = provider
        .and_then(|value| value.get("fallback_detected"))
        .and_then(Value::as_bool);

    let (execution_proven, classification) = if execution_proven && fallback_detected == Some(false)
    {
        (true, "strict_execution_proven")
    } else if stderr.contains("assigned to the default CPU EP")
        && stderr.contains("fallback to CPU EP has been explicitly disabled")
    {
        (false, "strict_rejected_cpu_assigned_nodes")
    } else {
        (false, "unknown_failure")
    };

    let mut result = json!({
        "provider": "coreml",
        "runner": "macos-14-arm64",
        "strict_provider_mode": true,
        "cpu_fallback_allowed": false,
        "step_outcome": step_outcome,
        "exit_code": exit_code,
        "execution_proven": execution_proven,
        "classification": classification
    });
    if let Some(provider) = provider {
        result
            .as_object_mut()
            .expect("result is an object")
            .insert("telemetry".to_owned(), Value::Object(provider.clone()));
    }
    result
}

fn classify_directml(metrics: Option<&Value>, step_outcome: &str, exit_code: &str) -> Value {
    let provider = metrics_provider(metrics);
    let execution_proven = provider
        .and_then(|value| value.get("execution_proven"))
        .and_then(Value::as_bool)
        == Some(true);

    let mut result = json!({
        "provider": "directml",
        "runner": "windows-latest",
        "strict_provider_mode": true,
        "cpu_fallback_allowed": false,
        "step_outcome": step_outcome,
        "exit_code": exit_code,
        "execution_proven": execution_proven
    });
    if let Some(provider) = provider {
        result
            .as_object_mut()
            .expect("result is an object")
            .insert("telemetry".to_owned(), Value::Object(provider.clone()));
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn coreml_proven_execution_is_classified() {
        let metrics = json!({
            "provider": {
                "execution_proven": true,
                "fallback_detected": false,
                "requested": "coreml"
            }
        });
        let result = classify_coreml(Some(&metrics), "success", "0");
        assert_eq!(result["execution_proven"], true);
        assert_eq!(result["classification"], "strict_execution_proven");
        assert_eq!(result["telemetry"]["requested"], "coreml");
    }

    #[test]
    fn coreml_cpu_assignment_rejection_is_classified() {
        let stderr = "nodes assigned to the default CPU EP; fallback to CPU EP has been explicitly disabled";
        let result = classify_coreml(None, stderr, "failure", "1");
        assert_eq!(result["execution_proven"], false);
        assert_eq!(
            result["classification"],
            "strict_rejected_cpu_assigned_nodes"
        );
    }

    #[test]
    fn directml_records_execution_proof_without_inventing_classification() {
        let metrics = json!({"provider": {"execution_proven": true}});
        let result = classify_directml(Some(&metrics), "success", "0");
        assert_eq!(result["execution_proven"], true);
        assert!(result.get("classification").is_none());
    }
}
