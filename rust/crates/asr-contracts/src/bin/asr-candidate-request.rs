use serde::Serialize;
use serde_json::{Map, Value};
use std::env;
use std::fs;
use std::path::PathBuf;

const ALLOWED_INPUT_FIELDS: &[&str] = &[
    "request_id",
    "request_execution_id",
    "source_repository",
    "receipt_repository",
    "hf_bucket",
    "candidate_id",
    "package_name",
    "dataset_source",
    "dataset_id",
    "suite",
    "executor",
    "environment",
    "hf_flavor",
    "hf_jobs_image",
    "dry_run",
];

#[derive(Debug, Serialize)]
struct ResolvedRequest {
    request_id: String,
    request_execution_id: String,
    source_repository: String,
    receipt_repository: String,
    hf_bucket: String,
    candidate_id: String,
    package_name: String,
    image: String,
    dataset_source: String,
    dataset_id: String,
    suite: String,
    executor: String,
    environment: String,
    provider: String,
    ort_package: String,
    hf_flavor: String,
    hf_jobs_image: String,
    dry_run: bool,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-candidate-request: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    if args.next().as_deref() != Some("resolve") {
        return Err(usage());
    }
    let mut inputs_json = "{}".to_owned();
    let mut config_json = "{}".to_owned();
    let mut default_namespace = String::new();
    let mut registry_owner = String::new();
    let mut github_output = None::<PathBuf>;

    while let Some(arg) = args.next() {
        let mut value = || args.next().ok_or_else(|| format!("{arg} requires a value"));
        match arg.as_str() {
            "--inputs-json" => inputs_json = value()?,
            "--config-json" => config_json = value()?,
            "--default-namespace" => default_namespace = value()?,
            "--registry-owner" => registry_owner = value()?,
            "--github-output" => github_output = Some(PathBuf::from(value()?)),
            other => return Err(format!("unsupported argument {other:?}")),
        }
    }

    let inputs = object(&inputs_json, "--inputs-json")?;
    let config = object(&config_json, "--config-json")?;
    let resolved = resolve(&inputs, &config, &default_namespace, &registry_owner)?;
    println!(
        "{}",
        serde_json::to_string(&resolved).map_err(|error| error.to_string())?
    );
    if let Some(path) = github_output {
        let mut lines = String::new();
        for (key, value) in [
            ("request_id", resolved.request_id.clone()),
            (
                "request_execution_id",
                resolved.request_execution_id.clone(),
            ),
            ("source_repository", resolved.source_repository.clone()),
            ("receipt_repository", resolved.receipt_repository.clone()),
            ("hf_bucket", resolved.hf_bucket.clone()),
            ("candidate_id", resolved.candidate_id.clone()),
            ("package_name", resolved.package_name.clone()),
            ("image", resolved.image.clone()),
            ("dataset_source", resolved.dataset_source.clone()),
            ("dataset_id", resolved.dataset_id.clone()),
            ("suite", resolved.suite.clone()),
            ("executor", resolved.executor.clone()),
            ("environment", resolved.environment.clone()),
            ("provider", resolved.provider.clone()),
            ("ort_package", resolved.ort_package.clone()),
            ("hf_flavor", resolved.hf_flavor.clone()),
            ("hf_jobs_image", resolved.hf_jobs_image.clone()),
        ] {
            lines.push_str(&format!("{key}={value}\n"));
        }
        lines.push_str(&format!("dry_run={}\n", resolved.dry_run));
        fs::write(&path, lines).map_err(|error| format!("{}: {error}", path.display()))?;
    }
    Ok(())
}

fn object(text: &str, name: &str) -> Result<Map<String, Value>, String> {
    serde_json::from_str::<Value>(text)
        .map_err(|error| format!("{name} is invalid JSON: {error}"))?
        .as_object()
        .cloned()
        .ok_or_else(|| format!("{name} must be a JSON object"))
}

fn string(map: &Map<String, Value>, key: &str) -> Result<String, String> {
    match map.get(key) {
        None | Some(Value::Null) => Ok(String::new()),
        Some(Value::String(value)) => Ok(value.clone()),
        Some(other) => Err(format!("input {key:?} must be string; got {other}")),
    }
}

fn boolean(map: &Map<String, Value>, key: &str, default: bool) -> Result<bool, String> {
    match map.get(key) {
        None | Some(Value::Null) => Ok(default),
        Some(Value::Bool(value)) => Ok(*value),
        Some(Value::String(value)) if value == "true" => Ok(true),
        Some(Value::String(value)) if value == "false" => Ok(false),
        Some(other) => Err(format!("input {key:?} must be boolean; got {other}")),
    }
}

fn reject_unknown_inputs(inputs: &Map<String, Value>) -> Result<(), String> {
    let mut unknown = inputs
        .keys()
        .filter(|key| !ALLOWED_INPUT_FIELDS.contains(&key.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    unknown.sort();
    if unknown.is_empty() {
        Ok(())
    } else {
        Err(format!("unsupported CandidateRequest fields: {unknown:?}"))
    }
}

fn nested_string(config: &Map<String, Value>, section: &str, key: &str) -> String {
    config
        .get(section)
        .and_then(Value::as_object)
        .and_then(|value| value.get(key))
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned()
}

fn choose(value: String, fallback: &str) -> String {
    if value.is_empty() {
        fallback.to_owned()
    } else {
        value
    }
}

fn require_choice(name: &str, value: &str, choices: &[&str]) -> Result<(), String> {
    if choices.contains(&value) {
        Ok(())
    } else {
        Err(format!("{name} must be one of {choices:?}; got {value:?}"))
    }
}

fn validate_repository(name: &str, field: &str) -> Result<(), String> {
    let mut parts = name.split('/');
    let owner = parts.next().unwrap_or_default();
    let repo = parts.next().unwrap_or_default();
    if owner.is_empty() || repo.is_empty() || parts.next().is_some() {
        return Err(format!("{field} must use owner/name"));
    }
    if [owner, repo].iter().any(|part| matches!(*part, "." | "..")) {
        return Err(format!("{field} must not contain dot path segments"));
    }
    if !name
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "._-/".contains(ch))
    {
        return Err(format!("{field} contains unsupported characters"));
    }
    Ok(())
}

fn validate_correlation_id(value: &str, field: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > 128 {
        return Err(format!("{field} must contain 1..128 characters"));
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "._:-".contains(ch))
    {
        return Err(format!("{field} contains unsupported characters"));
    }
    Ok(())
}

fn validate_safe_token(value: &str, field: &str, max_len: usize) -> Result<(), String> {
    if value.is_empty() || value.len() > max_len {
        return Err(format!("{field} must contain 1..{max_len} characters"));
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || ".-_".contains(ch))
    {
        return Err(format!("{field} contains unsupported characters"));
    }
    Ok(())
}

fn validate_digest_pinned_image(value: &str, field: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > 512 || value.chars().any(char::is_whitespace) {
        return Err(format!(
            "{field} is empty, too long, or contains whitespace"
        ));
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "./:@_-".contains(ch))
    {
        return Err(format!("{field} contains unsupported characters"));
    }
    let Some((name, digest)) = value.rsplit_once("@sha256:") else {
        return Err(format!(
            "{field} must be immutable and digest-pinned with @sha256:<64 hex>"
        ));
    };
    if name.is_empty()
        || digest.len() != 64
        || !digest
            .chars()
            .all(|ch| ch.is_ascii_hexdigit() && !ch.is_ascii_uppercase())
    {
        return Err(format!("{field} has an invalid lowercase sha256 digest"));
    }
    Ok(())
}

fn resolve(
    inputs: &Map<String, Value>,
    config: &Map<String, Value>,
    default_namespace: &str,
    registry_owner: &str,
) -> Result<ResolvedRequest, String> {
    reject_unknown_inputs(inputs)?;

    let request_id = string(inputs, "request_id")?;
    validate_correlation_id(&request_id, "request_id")?;
    let request_execution_id = string(inputs, "request_execution_id")?;
    validate_correlation_id(&request_execution_id, "request_execution_id")?;

    let source_repository = string(inputs, "source_repository")?;
    validate_repository(&source_repository, "source_repository")?;
    let source_owner = source_repository.split('/').next().unwrap_or_default();
    let repo_name = source_repository.split('/').nth(1).unwrap_or_default();

    let receipt_repository = choose(string(inputs, "receipt_repository")?, &source_repository);
    validate_repository(&receipt_repository, "receipt_repository")?;

    let mut hf_bucket = string(inputs, "hf_bucket")?;
    if hf_bucket.is_empty() {
        hf_bucket = config
            .get("hf_bucket")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
    }
    if hf_bucket.is_empty() {
        if default_namespace.is_empty() {
            return Err("cannot infer HF namespace".to_owned());
        }
        hf_bucket = format!("{default_namespace}/{repo_name}-bucket");
    }
    validate_repository(&hf_bucket, "hf_bucket")?;

    let mut candidate_id = string(inputs, "candidate_id")?;
    let explicit_latest = candidate_id == "latest";
    if explicit_latest {
        candidate_id.clear();
    }
    if candidate_id.is_empty() && !explicit_latest {
        let configured = nested_string(config, "candidate", "default");
        if !configured.is_empty() && configured != "latest" {
            candidate_id = configured;
        }
    }
    if !candidate_id.is_empty()
        && !(candidate_id.starts_with("candidate-")
            && candidate_id.len() == 16
            && candidate_id[10..].chars().all(|ch| ch.is_ascii_digit()))
    {
        return Err("candidate_id must be candidate-NNNNNN, latest, or blank".to_owned());
    }

    let configured_package = nested_string(config, "package", "default_name");
    let package_name = choose(
        choose(string(inputs, "package_name")?, &configured_package),
        repo_name,
    )
    .to_ascii_lowercase();
    if package_name.is_empty()
        || !package_name
            .chars()
            .all(|ch| ch.is_ascii_lowercase() || ch.is_ascii_digit() || ".-_".contains(ch))
    {
        return Err(format!("invalid package_name={package_name:?}"));
    }

    let mut dataset_source = choose(string(inputs, "dataset_source")?, "auto");
    if dataset_source == "auto" {
        dataset_source = choose(
            nested_string(config, "datasets", "default_source"),
            "bucket",
        );
    }
    require_choice(
        "dataset_source",
        &dataset_source,
        &["bucket", "repository", "custom"],
    )?;
    let mut dataset_id = string(inputs, "dataset_id")?;
    if dataset_source == "repository" && dataset_id.is_empty() {
        dataset_id = nested_string(config, "datasets", "repository_dataset");
    }
    if dataset_source == "bucket" {
        if !dataset_id.is_empty() {
            return Err("dataset_id must be empty for dataset_source=bucket".to_owned());
        }
    } else {
        validate_repository(&dataset_id, "dataset_id")?;
    }

    let suite = choose(string(inputs, "suite")?, "smoke");
    require_choice("suite", &suite, &["smoke", "parity", "probe"])?;
    let executor = choose(string(inputs, "executor")?, "github");
    require_choice("executor", &executor, &["github", "hf_jobs"])?;
    if executor == "hf_jobs" && suite != "smoke" {
        return Err("HF Jobs execution is smoke-only; suite must be smoke".to_owned());
    }

    let environment = choose(string(inputs, "environment")?, "linux-cpu");
    require_choice(
        "environment",
        &environment,
        &[
            "linux-cpu",
            "linux-cuda",
            "macos-coreml",
            "windows-directml",
        ],
    )?;
    if executor == "hf_jobs" && !environment.starts_with("linux-") {
        return Err("HF Jobs execution is restricted to Linux environments".to_owned());
    }

    let hf_flavor = choose(string(inputs, "hf_flavor")?, "cpu-basic");
    let hf_jobs_image = string(inputs, "hf_jobs_image")?;
    if executor == "hf_jobs" {
        validate_safe_token(&hf_flavor, "hf_flavor", 64)?;
        if !hf_jobs_image.is_empty() {
            validate_digest_pinned_image(&hf_jobs_image, "hf_jobs_image")?;
        }
    } else {
        if !hf_jobs_image.is_empty() {
            return Err("hf_jobs_image is only valid when executor=hf_jobs".to_owned());
        }
        if hf_flavor != "cpu-basic" {
            return Err("hf_flavor override is only valid when executor=hf_jobs".to_owned());
        }
    }

    let (provider, ort_package) = match environment.as_str() {
        "linux-cpu" => ("CPUExecutionProvider", "onnxruntime"),
        "linux-cuda" => ("CUDAExecutionProvider", "onnxruntime-gpu"),
        "macos-coreml" => ("CoreMLExecutionProvider", "onnxruntime"),
        "windows-directml" => ("DmlExecutionProvider", "onnxruntime-directml"),
        _ => unreachable!(),
    };
    let registry_owner = if registry_owner.is_empty() {
        source_owner
    } else {
        registry_owner
    };
    let image = format!(
        "ghcr.io/{}/{}",
        registry_owner.to_ascii_lowercase(),
        package_name
    );

    Ok(ResolvedRequest {
        request_id,
        request_execution_id,
        source_repository,
        receipt_repository,
        hf_bucket,
        candidate_id,
        package_name,
        image,
        dataset_source,
        dataset_id,
        suite,
        executor,
        environment,
        provider: provider.to_owned(),
        ort_package: ort_package.to_owned(),
        hf_flavor,
        hf_jobs_image,
        dry_run: boolean(inputs, "dry_run", false)?,
    })
}

fn usage() -> String {
    "usage: asr-candidate-request resolve --inputs-json JSON --config-json JSON --default-namespace NAME --registry-owner NAME [--github-output PATH]".to_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolves_completion_defaults() {
        let inputs = object(
            r#"{"request_id":"req-001","request_execution_id":"gw-100-1","source_repository":"owner/repo","dataset_source":"auto","suite":"smoke","executor":"github","environment":"linux-cpu"}"#,
            "inputs",
        )
        .unwrap();
        let resolved = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap();
        assert_eq!(resolved.request_execution_id, "gw-100-1");
        assert_eq!(resolved.hf_bucket, "hf-user/repo-bucket");
        assert_eq!(resolved.dataset_source, "bucket");
        assert_eq!(resolved.image, "ghcr.io/registry-owner/repo");
        assert_eq!(resolved.receipt_repository, "owner/repo");
    }

    #[test]
    fn rejects_unknown_candidate_request_fields_before_resolution() {
        for extra in [
            r#""unknown_scalar":1"#,
            r#""unknown_object":{"nested":true}"#,
            r#""unknown_null":null"#,
            r#""execute":true"#,
        ] {
            let inputs = object(
                &format!(
                    r#"{{"request_id":"req-unknown","request_execution_id":"gw-unknown-1","source_repository":"owner/repo",{extra}}}"#
                ),
                "inputs",
            )
            .unwrap();
            let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
            assert!(
                error.contains("unsupported CandidateRequest fields"),
                "{error}"
            );
        }
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
    fn explicit_latest_overrides_configured_candidate_default() {
        let inputs = object(
            r#"{"request_id":"req-latest","request_execution_id":"gw-103-1","source_repository":"owner/repo","candidate_id":"latest"}"#,
            "inputs",
        )
        .unwrap();
        let config = object(r#"{"candidate":{"default":"candidate-000777"}}"#, "config").unwrap();
        let resolved = resolve(&inputs, &config, "hf-user", "registry-owner").unwrap();
        assert_eq!(resolved.candidate_id, "");
    }

    #[test]
    fn rejects_non_linux_hf_jobs() {
        let inputs = object(
            r#"{"request_id":"req-002","request_execution_id":"gw-101-1","source_repository":"owner/repo","executor":"hf_jobs","suite":"smoke","environment":"macos-coreml"}"#,
            "inputs",
        )
        .unwrap();
        let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
        assert!(error.contains("Linux"));
    }

    #[test]
    fn rejects_non_smoke_hf_jobs_before_build() {
        for suite in ["probe", "parity"] {
            let inputs = object(
                &format!(
                    r#"{{"request_id":"req-hf-{suite}","request_execution_id":"gw-108-1","source_repository":"owner/repo","executor":"hf_jobs","suite":"{suite}","environment":"linux-cpu"}}"#
                ),
                "inputs",
            )
            .unwrap();
            let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
            assert!(error.contains("smoke-only"));
        }
    }

    #[test]
    fn github_executor_still_allows_probe_and_parity() {
        for suite in ["probe", "parity"] {
            let inputs = object(
                &format!(
                    r#"{{"request_id":"req-gh-{suite}","request_execution_id":"gw-109-1","source_repository":"owner/repo","executor":"github","suite":"{suite}","environment":"linux-cpu"}}"#
                ),
                "inputs",
            )
            .unwrap();
            let resolved = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap();
            assert_eq!(resolved.suite, suite);
            assert_eq!(resolved.executor, "github");
        }
    }

    #[test]
    fn rejects_hf_jobs_image_for_github_executor() {
        let image = format!("ghcr.io/owner/package@sha256:{}", "a".repeat(64));
        let inputs = object(
            &format!(
                r#"{{"request_id":"req-gh-hf-image","request_execution_id":"gw-110-1","source_repository":"owner/repo","executor":"github","hf_jobs_image":"{image}"}}"#
            ),
            "inputs",
        )
        .unwrap();
        let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
        assert!(error.contains("hf_jobs_image is only valid"), "{error}");
    }

    #[test]
    fn rejects_non_default_hf_flavor_for_github_executor() {
        let inputs = object(
            r#"{"request_id":"req-gh-hf-flavor","request_execution_id":"gw-111-1","source_repository":"owner/repo","executor":"github","hf_flavor":"a10g-small"}"#,
            "inputs",
        )
        .unwrap();
        let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
        assert!(
            error.contains("hf_flavor override is only valid"),
            "{error}"
        );
    }

    #[test]
    fn github_executor_accepts_compatibility_default_hf_flavor() {
        let inputs = object(
            r#"{"request_id":"req-gh-default-flavor","request_execution_id":"gw-112-1","source_repository":"owner/repo","executor":"github","hf_flavor":"cpu-basic"}"#,
            "inputs",
        )
        .unwrap();
        let resolved = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap();
        assert_eq!(resolved.hf_flavor, "cpu-basic");
        assert!(resolved.hf_jobs_image.is_empty());
    }

    #[test]
    fn rejects_unsafe_request_id() {
        let inputs = object(
            r#"{"request_id":"bad id","request_execution_id":"gw-102-1","source_repository":"owner/repo"}"#,
            "inputs",
        )
        .unwrap();
        let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
        assert!(error.contains("request_id"));
    }

    #[test]
    fn rejects_missing_execution_id() {
        let inputs = object(
            r#"{"request_id":"req-003","source_repository":"owner/repo"}"#,
            "inputs",
        )
        .unwrap();
        let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
        assert!(error.contains("request_execution_id"));
    }

    #[test]
    fn rejects_unsafe_hf_flavor_before_build() {
        let inputs = object(
            r#"{"request_id":"req-hf-flavor","request_execution_id":"gw-104-1","source_repository":"owner/repo","executor":"hf_jobs","suite":"smoke","environment":"linux-cpu","hf_flavor":"cpu basic"}"#,
            "inputs",
        )
        .unwrap();
        let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
        assert!(error.contains("hf_flavor"));
    }

    #[test]
    fn rejects_mutable_hf_jobs_image_before_build() {
        let inputs = object(
            r#"{"request_id":"req-hf-image","request_execution_id":"gw-105-1","source_repository":"owner/repo","executor":"hf_jobs","suite":"smoke","environment":"linux-cpu","hf_jobs_image":"ghcr.io/owner/package:latest"}"#,
            "inputs",
        )
        .unwrap();
        let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
        assert!(error.contains("digest-pinned"));
    }

    #[test]
    fn rejects_uppercase_hf_jobs_image_digest_before_build() {
        let image = format!("ghcr.io/owner/package@sha256:{}", "A".repeat(64));
        let inputs = object(
            &format!(
                r#"{{"request_id":"req-hf-image-upper","request_execution_id":"gw-105-2","source_repository":"owner/repo","executor":"hf_jobs","suite":"smoke","environment":"linux-cpu","hf_jobs_image":"{image}"}}"#
            ),
            "inputs",
        )
        .unwrap();
        let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
        assert!(error.contains("lowercase sha256"));
    }

    #[test]
    fn accepts_digest_pinned_hf_jobs_image() {
        let image = format!("ghcr.io/owner/package@sha256:{}", "a".repeat(64));
        let inputs = object(
            &format!(
                r#"{{"request_id":"req-hf-image-ok","request_execution_id":"gw-106-1","source_repository":"owner/repo","executor":"hf_jobs","suite":"smoke","environment":"linux-cpu","hf_jobs_image":"{image}"}}"#
            ),
            "inputs",
        )
        .unwrap();
        let resolved = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap();
        assert_eq!(resolved.hf_jobs_image, image);
        assert_eq!(resolved.suite, "smoke");
    }

    #[test]
    fn rejects_malformed_dataset_id_before_build() {
        let inputs = object(
            r#"{"request_id":"req-dataset","request_execution_id":"gw-107-1","source_repository":"owner/repo","executor":"hf_jobs","suite":"smoke","environment":"linux-cpu","dataset_source":"custom","dataset_id":"not-a-repository"}"#,
            "inputs",
        )
        .unwrap();
        let error = resolve(&inputs, &Map::new(), "hf-user", "registry-owner").unwrap_err();
        assert!(error.contains("dataset_id"));
    }
}
