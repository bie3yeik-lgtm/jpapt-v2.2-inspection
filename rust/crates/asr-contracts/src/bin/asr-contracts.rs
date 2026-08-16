use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use asr_contracts::{
    ContractError, Result, validate_benchmark, validate_run_context, validate_run_directory,
    validate_sample_result,
};
use serde_json::{Value, json};

#[path = "../project_config.rs"]
mod project_config;
#[path = "../revisions.rs"]
mod revisions;
#[path = "../run_context_builder.rs"]
mod run_context_builder;

use revisions::{RevisionExpectations, validate_revision_bundle};
use run_context_builder::{RunContextBuildOptions, build_run_context, write_run_context};

fn usage() -> &'static str {
    "usage:\n  asr-contracts validate-run <run-directory> [--json]\n  asr-contracts validate-run-context <run-context.json>\n  asr-contracts validate-benchmark <metrics.json>\n  asr-contracts validate-sample <result.json>\n  asr-contracts validate-revisions --root <revisions-dir> [--expected-development-repo-id <id>] [--expected-upstream-repo-id <id>] [--expected-tokenizer-repo-id <id>] [--expected-framework <name>] [--expected-profile-set <id>] [--runtime-variant <variant>] [--expected-runtime-profile <id>] [--expected-decoder <decoder>] [--json]\n  asr-contracts resolve-config --current <current.json> --resolved <resolved.json> [--override <config-NNNNNN>]\n  asr-contracts config-version <resolved.json>\n  asr-contracts build-run-context --repository-root <repo> --model <id> --provider <id> --evaluation <id> --environment <id> --revisions <dir> --candidate-contract <json> --output <json> [--runtime-variant <variant>] [--experiment-id <id>] [--strict-provider] [--optimization-level <configured|disable|basic|extended|all>]"
}

fn read_json(path: &Path) -> std::result::Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    serde_json::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))
}

fn take_value(
    args: &mut impl Iterator<Item = String>,
    option: &str,
) -> std::result::Result<String, String> {
    args.next()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{option} requires a non-empty value"))
}

fn is_config_version(value: &str) -> bool {
    value.len() == 13
        && value.starts_with("config-")
        && value[7..].bytes().all(|byte| byte.is_ascii_digit())
}

fn require_config_document(path: &Path) -> std::result::Result<Value, String> {
    let value = read_json(path)?;
    let object = value
        .as_object()
        .ok_or_else(|| format!("{} root must be an object", path.display()))?;
    if object.get("schema_version").and_then(Value::as_u64) != Some(1) {
        return Err(format!("{} schema_version must equal 1", path.display()));
    }
    Ok(value)
}

fn config_version_from(value: &Value, label: &str) -> std::result::Result<String, String> {
    let version = value
        .get("config_version")
        .and_then(Value::as_str)
        .ok_or_else(|| format!("{label} config_version must be a string"))?;
    if !is_config_version(version) {
        return Err(format!(
            "{label} config_version must match config-NNNNNN; got {version:?}"
        ));
    }
    Ok(version.to_owned())
}

fn resolve_config_command(
    mut args: impl Iterator<Item = String>,
) -> std::result::Result<(), String> {
    let mut current = None;
    let mut resolved = None;
    let mut override_version = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--current" => current = Some(PathBuf::from(take_value(&mut args, "--current")?)),
            "--resolved" => resolved = Some(PathBuf::from(take_value(&mut args, "--resolved")?)),
            "--override" => override_version = Some(take_value(&mut args, "--override")?),
            other => return Err(format!("unsupported argument: {other}\n{}", usage())),
        }
    }
    let current = current.ok_or_else(|| "--current is required".to_owned())?;
    let resolved = resolved.ok_or_else(|| "--resolved is required".to_owned())?;
    let current_value = require_config_document(&current)?;
    let current_version = config_version_from(&current_value, "config/current.json")?;
    let (selected, source) = match override_version {
        Some(value) => {
            if !is_config_version(&value) {
                return Err(format!(
                    "--override must match config-NNNNNN; got {value:?}"
                ));
            }
            (value, "override")
        }
        None => (current_version.clone(), "current"),
    };
    if let Some(parent) = resolved.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("{}: {error}", parent.display()))?;
    }
    let payload = json!({
        "schema_version": 1,
        "config_version": selected,
        "current_version": current_version,
        "selection_source": source,
    });
    let bytes = serde_json::to_vec_pretty(&payload).map_err(|error| error.to_string())?;
    let temporary = resolved.with_extension("json.tmp");
    fs::write(&temporary, [bytes.as_slice(), b"\n"].concat())
        .map_err(|error| format!("{}: {error}", temporary.display()))?;
    fs::rename(&temporary, &resolved)
        .map_err(|error| format!("{}: {error}", resolved.display()))?;
    println!("{}", payload["config_version"].as_str().expect("string"));
    Ok(())
}

fn config_version_command(
    mut args: impl Iterator<Item = String>,
) -> std::result::Result<(), String> {
    let path = args
        .next()
        .map(PathBuf::from)
        .ok_or_else(|| usage().to_owned())?;
    if args.next().is_some() {
        return Err(usage().to_owned());
    }
    let value = require_config_document(&path)?;
    println!(
        "{}",
        config_version_from(&value, &path.display().to_string())?
    );
    Ok(())
}

fn validate_revisions_command(
    mut args: impl Iterator<Item = String>,
) -> std::result::Result<(), String> {
    let mut root = None;
    let mut json = false;
    let mut expectations = RevisionExpectations::empty();

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--root" => root = Some(PathBuf::from(take_value(&mut args, "--root")?)),
            "--expected-development-repo-id" => {
                expectations.development_repo_id =
                    Some(take_value(&mut args, "--expected-development-repo-id")?)
            }
            "--expected-upstream-repo-id" => {
                expectations.upstream_repo_id =
                    Some(take_value(&mut args, "--expected-upstream-repo-id")?)
            }
            "--expected-tokenizer-repo-id" => {
                expectations.tokenizer_repo_id =
                    Some(take_value(&mut args, "--expected-tokenizer-repo-id")?)
            }
            "--expected-framework" => {
                expectations.canonical_framework =
                    Some(take_value(&mut args, "--expected-framework")?)
            }
            "--expected-profile-set" => {
                expectations.profile_set = Some(take_value(&mut args, "--expected-profile-set")?)
            }
            "--runtime-variant" => {
                expectations.runtime_variant = Some(take_value(&mut args, "--runtime-variant")?)
            }
            "--expected-runtime-profile" => {
                expectations.runtime_profile =
                    Some(take_value(&mut args, "--expected-runtime-profile")?)
            }
            "--expected-decoder" => {
                expectations.decoder = Some(take_value(&mut args, "--expected-decoder")?)
            }
            "--json" => json = true,
            other => return Err(format!("unsupported argument: {other}\n{}", usage())),
        }
    }

    let root = root.ok_or_else(|| "--root is required".to_owned())?;
    let (snapshot, resolution) =
        validate_revision_bundle(&root, &expectations).map_err(|error| error.to_string())?;

    if json {
        println!(
            "{}",
            serde_json::to_string_pretty(&snapshot).map_err(|error| error.to_string())?
        );
    } else {
        println!("Revision documents are valid.");
        println!("root={}", root.display());
        println!("config_version={}", snapshot.config_version);
        println!("bundle_sha256={}", snapshot.bundle_sha256);
        println!(
            "development_artifact={}@{}",
            snapshot.reference.development_artifact.repo_id,
            snapshot.reference.development_artifact.revision
        );
        println!(
            "upstream={}@{}",
            snapshot.reference.upstream.repo_id, snapshot.reference.upstream.revision
        );
        println!(
            "tokenizer={}@{}",
            snapshot.reference.tokenizer.repo_id, snapshot.reference.tokenizer.revision
        );
        println!(
            "canonical_framework={}",
            snapshot.reference.canonical_framework
        );
        println!("runtime_profile_set={}", snapshot.runtime.profile_set);
        println!("runtime_variant={}", resolution.variant);
        println!("runtime_profile={}", resolution.profile);
        println!("decoder={}", resolution.decoder);
        println!("datasets={}", snapshot.datasets.entries.len());
    }
    Ok(())
}

fn build_run_context_command(
    mut args: impl Iterator<Item = String>,
) -> std::result::Result<(), String> {
    let mut repository_root = None;
    let mut model_id = None;
    let mut provider_id = None;
    let mut evaluation_id = None;
    let mut environment_id = None;
    let mut revisions_root = None;
    let mut candidate_contract = None;
    let mut output = None;
    let mut experiment_id = None;
    let mut runtime_variant = None;
    let mut strict_provider = false;
    let mut optimization_level = "configured".to_owned();

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--repository-root" => {
                repository_root = Some(PathBuf::from(take_value(&mut args, "--repository-root")?))
            }
            "--model" => model_id = Some(take_value(&mut args, "--model")?),
            "--provider" => provider_id = Some(take_value(&mut args, "--provider")?),
            "--evaluation" => evaluation_id = Some(take_value(&mut args, "--evaluation")?),
            "--environment" => environment_id = Some(take_value(&mut args, "--environment")?),
            "--revisions" => {
                revisions_root = Some(PathBuf::from(take_value(&mut args, "--revisions")?))
            }
            "--candidate-contract" => {
                candidate_contract = Some(PathBuf::from(take_value(
                    &mut args,
                    "--candidate-contract",
                )?))
            }
            "--output" => output = Some(PathBuf::from(take_value(&mut args, "--output")?)),
            "--experiment-id" => experiment_id = Some(take_value(&mut args, "--experiment-id")?),
            "--runtime-variant" => {
                runtime_variant = Some(take_value(&mut args, "--runtime-variant")?)
            }
            "--strict-provider" => strict_provider = true,
            "--optimization-level" => {
                optimization_level = take_value(&mut args, "--optimization-level")?
            }
            other => return Err(format!("unsupported argument: {other}\n{}", usage())),
        }
    }

    let repository_root = repository_root.unwrap_or_else(|| PathBuf::from("."));
    let candidate_contract =
        candidate_contract.ok_or_else(|| "--candidate-contract is required".to_owned())?;
    if let Some(expected_variant) = runtime_variant.as_deref() {
        let candidate = read_json(&candidate_contract)?;
        let actual = candidate
            .get("variant")
            .and_then(Value::as_str)
            .ok_or_else(|| "candidate contract variant must be a string".to_owned())?;
        if expected_variant != actual {
            return Err(format!(
                "candidate contract variant mismatch: expected={expected_variant:?}, actual={actual:?}"
            ));
        }
    }
    let options = RunContextBuildOptions {
        repository_root,
        model_id: model_id.ok_or_else(|| "--model is required".to_owned())?,
        provider_id: provider_id.ok_or_else(|| "--provider is required".to_owned())?,
        evaluation_id: evaluation_id.ok_or_else(|| "--evaluation is required".to_owned())?,
        environment_id: environment_id.ok_or_else(|| "--environment is required".to_owned())?,
        revisions_root: revisions_root.ok_or_else(|| "--revisions is required".to_owned())?,
        candidate_contract,
        strict_provider,
        optimization_level,
        experiment_id,
    };
    let output = output.ok_or_else(|| "--output is required".to_owned())?;
    let context = build_run_context(&options).map_err(|error| error.to_string())?;
    write_run_context(&output, &context).map_err(|error| error.to_string())?;
    println!("run_context={}", output.display());
    println!(
        "run_id={}",
        context
            .get("run_id")
            .and_then(Value::as_str)
            .expect("validated run context run_id")
    );
    Ok(())
}

fn run() -> std::result::Result<(), String> {
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
        "validate-revisions" => validate_revisions_command(args)?,
        "resolve-config" => resolve_config_command(args)?,
        "config-version" => config_version_command(args)?,
        "build-run-context" => build_run_context_command(args)?,
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
