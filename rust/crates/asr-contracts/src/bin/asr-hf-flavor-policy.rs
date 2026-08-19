use serde_json::Value;
use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-hf-flavor-policy: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    if args.next().as_deref() != Some("validate") {
        return Err(usage());
    }
    if args.next().as_deref() != Some("--plan") {
        return Err(usage());
    }
    let plan_path = PathBuf::from(args.next().ok_or_else(usage)?);
    if args.next().is_some() {
        return Err(usage());
    }

    let text = fs::read_to_string(&plan_path)
        .map_err(|error| format!("{}: {error}", plan_path.display()))?;
    let value: Value = serde_json::from_str(&text)
        .map_err(|error| format!("{}: invalid JSON: {error}", plan_path.display()))?;
    let plan = value
        .as_object()
        .ok_or_else(|| "HF Jobs plan must be a JSON object".to_owned())?;

    let environment = required_string(plan, "environment")?;
    let provider = required_string(plan, "provider")?;
    let flavor = required_string(plan, "flavor")?;
    validate_binding(environment, provider, flavor)?;
    println!("environment={environment} provider={provider} flavor={flavor}");
    Ok(())
}

fn usage() -> String {
    "usage: asr-hf-flavor-policy validate --plan PATH".to_owned()
}

fn required_string<'a>(
    plan: &'a serde_json::Map<String, Value>,
    field: &str,
) -> Result<&'a str, String> {
    plan.get(field)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("HF Jobs plan {field} must be a non-empty string"))
}

fn validate_binding(environment: &str, provider: &str, flavor: &str) -> Result<(), String> {
    let cpu_flavor = flavor.starts_with("cpu-");
    match (environment, provider) {
        ("linux-cpu", "CPUExecutionProvider") if cpu_flavor => Ok(()),
        ("linux-cpu", "CPUExecutionProvider") => Err(format!(
            "linux-cpu HF Jobs requires a cpu-* flavor; got {flavor:?}"
        )),
        ("linux-cuda", "CUDAExecutionProvider") if !cpu_flavor => Ok(()),
        ("linux-cuda", "CUDAExecutionProvider") => Err(format!(
            "linux-cuda HF Jobs must not use a cpu-* flavor; got {flavor:?}"
        )),
        ("linux-cpu", _) => Err("linux-cpu HF Jobs requires CPUExecutionProvider".to_owned()),
        ("linux-cuda", _) => Err("linux-cuda HF Jobs requires CUDAExecutionProvider".to_owned()),
        _ => Err(format!(
            "HF Jobs flavor policy only supports linux-cpu or linux-cuda; got environment={environment:?}"
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_canonical_cpu_and_cuda_bindings() {
        validate_binding("linux-cpu", "CPUExecutionProvider", "cpu-basic").unwrap();
        validate_binding("linux-cpu", "CPUExecutionProvider", "cpu-performance").unwrap();
        validate_binding("linux-cuda", "CUDAExecutionProvider", "a10g-small").unwrap();
        validate_binding("linux-cuda", "CUDAExecutionProvider", "t4-small").unwrap();
    }

    #[test]
    fn rejects_cpu_flavor_for_cuda_before_paid_execution() {
        let error =
            validate_binding("linux-cuda", "CUDAExecutionProvider", "cpu-basic").unwrap_err();
        assert!(error.contains("must not use a cpu-* flavor"), "{error}");
    }

    #[test]
    fn rejects_gpu_flavor_for_cpu_before_paid_execution() {
        let error =
            validate_binding("linux-cpu", "CPUExecutionProvider", "a10g-small").unwrap_err();
        assert!(error.contains("requires a cpu-* flavor"), "{error}");
    }

    #[test]
    fn rejects_environment_provider_mismatch() {
        assert!(validate_binding("linux-cpu", "CUDAExecutionProvider", "cpu-basic").is_err());
        assert!(validate_binding("linux-cuda", "CPUExecutionProvider", "a10g-small").is_err());
    }
}
