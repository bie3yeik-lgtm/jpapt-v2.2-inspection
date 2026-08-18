use serde_json::Value;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-hf-smoke-result: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    if args.next().as_deref() != Some("validate") {
        return Err(usage());
    }
    let mut plan_path = None::<PathBuf>;
    let mut result_path = None::<PathBuf>;
    while let Some(flag) = args.next() {
        let value = args
            .next()
            .ok_or_else(|| format!("{flag} requires a value"))?;
        match flag.as_str() {
            "--plan" => plan_path = Some(PathBuf::from(value)),
            "--result" => result_path = Some(PathBuf::from(value)),
            other => return Err(format!("unsupported argument {other:?}")),
        }
    }
    let plan_path = plan_path.ok_or_else(usage)?;
    let result_path = result_path.ok_or_else(usage)?;
    let plan = read_json(&plan_path)?;
    let result = read_json(&result_path)?;
    let summary = validate_smoke_result(&plan, &result)?;
    println!(
        "{}",
        serde_json::to_string(&summary).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn usage() -> String {
    "usage: asr-hf-smoke-result validate --plan PATH --result PATH".to_owned()
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    serde_json::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))
}

fn required_object<'a>(value: &'a Value, label: &str) -> Result<&'a serde_json::Map<String, Value>, String> {
    value
        .as_object()
        .ok_or_else(|| format!("{label} must be a JSON object"))
}

fn required_string<'a>(
    object: &'a serde_json::Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<&'a str, String> {
    object
        .get(field)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{label}.{field} must be a non-empty string"))
}

fn required_bool(
    object: &serde_json::Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<bool, String> {
    object
        .get(field)
        .and_then(Value::as_bool)
        .ok_or_else(|| format!("{label}.{field} must be boolean"))
}

fn required_u64(
    object: &serde_json::Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<u64, String> {
    object
        .get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| format!("{label}.{field} must be an unsigned integer"))
}

fn validate_smoke_result(plan: &Value, result: &Value) -> Result<Value, String> {
    let plan = required_object(plan, "plan")?;
    let result = required_object(result, "result")?;

    if required_u64(plan, "schema_version", "plan")? != 2 {
        return Err("plan.schema_version must be 2".to_owned());
    }
    if required_string(plan, "suite", "plan")? != "smoke" {
        return Err("plan suite must be smoke".to_owned());
    }
    let provider = required_string(plan, "provider", "plan")?;
    let candidate_id = required_string(plan, "candidate_id", "plan")?;
    let result_uri = required_string(plan, "result_uri", "plan")?;

    if required_u64(result, "schema_version", "result")? != 2 {
        return Err("result.schema_version must be 2".to_owned());
    }
    if required_string(result, "suite", "result")? != "smoke" {
        return Err("HF Jobs result suite must be smoke".to_owned());
    }
    if required_string(result, "requested_provider", "result")? != provider {
        return Err("result.requested_provider does not match the HF Jobs plan".to_owned());
    }
    if !required_bool(result, "requested_provider_available", "result")? {
        return Err("requested provider was unavailable in the HF Jobs smoke result".to_owned());
    }
    if required_string(result, "provider", "result")? != provider {
        return Err("result.provider does not match the strict requested provider".to_owned());
    }
    if required_bool(result, "provider_fallback", "result")? {
        return Err("provider fallback is not permitted in HF Jobs smoke evidence".to_owned());
    }
    if !required_bool(result, "passed", "result")? {
        return Err(format!(
            "HF Jobs smoke result did not pass: failure={}",
            result
                .get("failure")
                .and_then(Value::as_str)
                .unwrap_or("unspecified")
        ));
    }
    if result.get("failure").is_some_and(|value| !value.is_null()) {
        return Err("passed HF Jobs smoke result must not contain failure evidence".to_owned());
    }

    let models = result
        .get("models")
        .and_then(Value::as_array)
        .filter(|models| !models.is_empty())
        .ok_or_else(|| "HF Jobs smoke result must contain at least one model".to_owned())?;
    for (index, model) in models.iter().enumerate() {
        let model = required_object(model, &format!("result.models[{index}]"))?;
        if !required_bool(model, "passed", &format!("result.models[{index}]"))? {
            return Err(format!("result.models[{index}] did not pass"));
        }
        let active = model
            .get("active_providers")
            .and_then(Value::as_array)
            .ok_or_else(|| format!("result.models[{index}].active_providers must be an array"))?;
        if !active.iter().any(|value| value.as_str() == Some(provider)) {
            return Err(format!(
                "result.models[{index}] does not register requested provider {provider}"
            ));
        }
    }

    let cases = result
        .get("cases")
        .and_then(Value::as_array)
        .filter(|cases| !cases.is_empty())
        .ok_or_else(|| "HF Jobs smoke result must contain smoke case evidence".to_owned())?;
    for (index, case) in cases.iter().enumerate() {
        let case = required_object(case, &format!("result.cases[{index}]"))?;
        if !required_bool(case, "passed", &format!("result.cases[{index}]"))? {
            return Err(format!("result.cases[{index}] did not pass"));
        }
    }

    Ok(serde_json::json!({
        "schema_version": 1,
        "suite": "smoke",
        "candidate_id": candidate_id,
        "provider": provider,
        "result_uri": result_uri,
        "model_count": models.len(),
        "case_count": cases.len(),
        "passed": true
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn plan() -> Value {
        serde_json::json!({
            "schema_version": 2,
            "suite": "smoke",
            "provider": "CPUExecutionProvider",
            "candidate_id": "candidate-000123",
            "result_uri": "hf://buckets/owner/bucket/runs/hf-jobs/candidate-000123/smoke-1-1/result.json"
        })
    }

    fn result() -> Value {
        serde_json::json!({
            "schema_version": 2,
            "suite": "smoke",
            "requested_provider": "CPUExecutionProvider",
            "requested_provider_available": true,
            "provider": "CPUExecutionProvider",
            "provider_fallback": false,
            "available_providers": ["CPUExecutionProvider"],
            "models": [{
                "path": "encoder.onnx",
                "passed": true,
                "active_providers": ["CPUExecutionProvider"]
            }],
            "cases": [{"case": null, "passed": true, "note": "structural smoke"}],
            "passed": true
        })
    }

    #[test]
    fn accepts_strict_smoke_evidence() {
        let summary = validate_smoke_result(&plan(), &result()).unwrap();
        assert_eq!(summary["passed"], true);
        assert_eq!(summary["model_count"], 1);
        assert_eq!(summary["case_count"], 1);
    }

    #[test]
    fn rejects_provider_fallback() {
        let mut result = result();
        result["provider_fallback"] = Value::Bool(true);
        assert!(validate_smoke_result(&plan(), &result).unwrap_err().contains("fallback"));
    }

    #[test]
    fn rejects_wrong_suite_or_provider() {
        let mut result = result();
        result["suite"] = Value::String("probe".to_owned());
        assert!(validate_smoke_result(&plan(), &result).unwrap_err().contains("suite"));

        let mut result = result();
        result["provider"] = Value::String("CUDAExecutionProvider".to_owned());
        assert!(validate_smoke_result(&plan(), &result).unwrap_err().contains("provider"));
    }

    #[test]
    fn rejects_failed_model_or_case() {
        let mut result = result();
        result["models"][0]["passed"] = Value::Bool(false);
        assert!(validate_smoke_result(&plan(), &result).unwrap_err().contains("models[0]"));

        let mut result = result();
        result["cases"][0]["passed"] = Value::Bool(false);
        assert!(validate_smoke_result(&plan(), &result).unwrap_err().contains("cases[0]"));
    }
}
