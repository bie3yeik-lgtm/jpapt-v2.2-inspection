use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use asr_contracts::validate_run_context;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-provider-probe-context: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut contract = None;
    let mut provider = None;
    let mut output = None;

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--contract" => contract = Some(PathBuf::from(take_value(&mut args, "--contract")?)),
            "--provider" => provider = Some(take_value(&mut args, "--provider")?),
            "--output" => output = Some(PathBuf::from(take_value(&mut args, "--output")?)),
            other => return Err(format!("unsupported argument {other:?}\n{}", usage())),
        }
    }

    let contract_path = contract.ok_or_else(|| "--contract is required".to_owned())?;
    let provider = provider.ok_or_else(|| "--provider is required".to_owned())?;
    let output = output.ok_or_else(|| "--output is required".to_owned())?;
    let provider_ort_name = provider_ort_name(&provider)?;

    let contract = read_json(&contract_path)?;
    let primary = contract
        .pointer("/artifacts/primary")
        .and_then(Value::as_object)
        .ok_or_else(|| "candidate contract must contain artifacts.primary".to_owned())?;
    let candidate_root = required_string(&contract, "/candidate_root", "candidate_root")?;
    let artifact_path = required_object_string(primary, "path", "artifacts.primary.path")?;
    let model_path = Path::new(candidate_root).join(artifact_path);
    if !model_path.is_file() {
        return Err(format!(
            "candidate primary artifact is missing: {}",
            model_path.display()
        ));
    }

    let candidate_id = required_string(&contract, "/candidate_id", "candidate_id")?;
    let profile_set = required_string(&contract, "/profile_set", "profile_set")?;
    let catalog_id = required_string(&contract, "/catalog/id", "catalog.id")?;
    let catalog_sha256 = required_string(&contract, "/catalog/sha256", "catalog.sha256")?;
    let artifact_sha256 = required_object_string(primary, "sha256", "artifacts.primary.sha256")?;
    let artifact_size = primary
        .get("size_bytes")
        .and_then(Value::as_u64)
        .filter(|value| *value > 0)
        .ok_or_else(|| "artifacts.primary.size_bytes must be a positive integer".to_owned())?;

    let host_os = host_os_id();
    let revisions = revision_snapshot(profile_set, catalog_id, catalog_sha256, artifact_sha256)?;
    let provenance = revisions
        .pointer("/provenance")
        .cloned()
        .ok_or_else(|| "provider probe revision snapshot is missing provenance".to_owned())?;
    let git_commit = git_commit()?;
    let config_identity = "strict-provider-probe-v1";
    let model_id = "synthetic-strict-provider-ctc";
    let enable_mem_pattern = provider != "directml";

    let context = json!({
        "schema_version": 2,
        "run_id": format!("strict-provider-probe-{provider}"),
        "created_at": "2026-08-16T00:00:00Z",
        "config_identity": config_identity,
        "model_id": model_id,
        "environment_id": host_os,
        "provider_id": provider,
        "evaluation_id": "smoke",
        "artifact": {
            "path": model_path.canonicalize().map_err(|error| format!("{}: {error}", model_path.display()))?.to_string_lossy(),
            "sha256": artifact_sha256,
            "size_bytes": artifact_size,
            "candidate_id": candidate_id,
            "artifact_role": "primary"
        },
        "git": {
            "repository": nonempty_env("GITHUB_REPOSITORY", "bie3yeik-lgtm/jpapt-v2.2-inspection"),
            "commit": git_commit,
            "ref": nonempty_env("GITHUB_REF_NAME", "agent/provider-strict-probes"),
            "dirty": false
        },
        "host": {
            "os": host_os,
            "architecture": env::consts::ARCH,
            "hostname": hostname(),
            "python_version": "not-applicable",
            "implementation": "Rust",
            "is_wsl": false,
            "github_runner_os": nonempty_env("RUNNER_OS", host_os),
            "github_runner_arch": nonempty_env("RUNNER_ARCH", env::consts::ARCH),
            "github_run_id": nonempty_env("GITHUB_RUN_ID", "local"),
            "github_run_attempt": nonempty_env("GITHUB_RUN_ATTEMPT", "1")
        },
        "runtime": {
            "implementation": "rust",
            "backend": "onnxruntime",
            "backend_version": "resolved-by-rust-runtime",
            "provider_id": provider,
            "provider_ort_name": provider_ort_name,
            "provider_available": false
        },
        "revisions": revisions,
        "config": {
            "identity": config_identity,
            "sources": {
                "model": "generated/provider-probe",
                "provider": format!("generated/provider-probe/{provider}"),
                "environment": format!("generated/provider-probe/{host_os}"),
                "evaluation": "generated/provider-probe/smoke"
            },
            "resolved": {
                "model": {},
                "provider": {
                    "session": {
                        "graph_optimization_level": "all",
                        "execution_mode": "sequential",
                        "enable_mem_pattern": enable_mem_pattern
                    },
                    "validation": {
                        "allow_cpu_fallback": false,
                        "strict_provider_mode": true
                    }
                },
                "environment": {
                    "runtime": {
                        "cpu": {"intra_op_threads": 0, "inter_op_threads": 0}
                    }
                },
                "evaluation": {},
                "resolved": {
                    "model_id": model_id,
                    "provider_id": provider,
                    "environment_id": host_os,
                    "evaluation_id": "smoke"
                }
            }
        },
        "metadata": {
            "candidate": contract,
            "purpose": "strict non-CPU execution-provider readiness probe",
            "provenance": {
                "manifest_sha256": provenance["manifest_sha256"].clone(),
                "status": "complete",
                "automation_consumption": true,
                "target_id": "parakeet-tdt_ctc-0.6b-ja"
            }
        }
    });

    validate_run_context(&context).map_err(|error| error.to_string())?;
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("{}: {error}", parent.display()))?;
    }
    let mut bytes = serde_json::to_vec_pretty(&context).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(&output, bytes).map_err(|error| format!("{}: {error}", output.display()))?;
    println!("Provider probe run context: {}", output.display());
    Ok(())
}

fn usage() -> &'static str {
    "usage: asr-provider-probe-context --contract <candidate-contract.json> --provider <cpu|cuda|directml|coreml> --output <run-context.json>"
}

fn take_value(args: &mut impl Iterator<Item = String>, option: &str) -> Result<String, String> {
    args.next()
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| format!("{option} requires a non-empty value"))
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    serde_json::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))
}

fn required_string<'a>(value: &'a Value, pointer: &str, name: &str) -> Result<&'a str, String> {
    value
        .pointer(pointer)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| format!("{name} must be a non-empty string"))
}

fn required_object_string<'a>(
    value: &'a serde_json::Map<String, Value>,
    key: &str,
    name: &str,
) -> Result<&'a str, String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| format!("{name} must be a non-empty string"))
}

fn provider_ort_name(provider: &str) -> Result<&'static str, String> {
    match provider {
        "cpu" => Ok("CPUExecutionProvider"),
        "cuda" => Ok("CUDAExecutionProvider"),
        "directml" => Ok("DmlExecutionProvider"),
        "coreml" => Ok("CoreMLExecutionProvider"),
        other => Err(format!("unsupported provider {other:?}")),
    }
}

fn host_os_id() -> &'static str {
    if cfg!(target_os = "macos") {
        "macos"
    } else if cfg!(target_os = "windows") {
        "windows"
    } else {
        "linux"
    }
}

fn nonempty_env(name: &str, fallback: &str) -> String {
    env::var(name)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| fallback.to_owned())
}

fn hostname() -> String {
    for name in ["RUNNER_NAME", "HOSTNAME", "COMPUTERNAME"] {
        if let Ok(value) = env::var(name)
            && !value.trim().is_empty()
        {
            return value;
        }
    }
    "github-runner".to_owned()
}

fn git_commit() -> Result<String, String> {
    let value = env::var("GITHUB_SHA")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .or_else(|| {
            Command::new("git")
                .args(["rev-parse", "HEAD"])
                .output()
                .ok()
                .filter(|output| output.status.success())
                .and_then(|output| String::from_utf8(output.stdout).ok())
                .map(|value| value.trim().to_owned())
        })
        .ok_or_else(|| "provider probe requires a concrete Git commit".to_owned())?;
    if !(7..=64).contains(&value.len()) || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(format!("invalid Git commit identity: {value:?}"));
    }
    Ok(value.to_ascii_lowercase())
}

fn revision_snapshot(
    profile_set: &str,
    catalog_id: &str,
    catalog_sha256: &str,
    artifact_sha256: &str,
) -> Result<Value, String> {
    let runtime_document = json!({
        "schema_version": 1,
        "catalog": {"id": catalog_id, "sha256": catalog_sha256},
        "profile_set": profile_set
    });
    let reference_document = json!({
        "schema_version": 1,
        "development_artifact": {"repo_id": "generated/provider-probe", "revision": "synthetic-v1"},
        "upstream": {"repo_id": "generated/provider-probe", "revision": "synthetic-v1"},
        "tokenizer": {"repo_id": "generated/provider-probe-tokenizer", "revision": "synthetic-v1"},
        "reference": {
            "id": "provider-probe-reference",
            "revision": "synthetic-v1",
            "canonical_framework": "generated"
        }
    });
    let evaluation_document = json!({
        "schema_version": 1,
        "schema": {"id": "provider-probe-smoke", "revision": "synthetic-v1"},
        "artifact_contract": "ctc-single-graph-v1"
    });
    let datasets_document = json!({"schema_version": 1, "datasets": []});

    let reference_hash = canonical_sha256(&reference_document)?;
    let evaluation_hash = canonical_sha256(&evaluation_document)?;
    let datasets_hash = canonical_sha256(&datasets_document)?;
    let runtime_hash = canonical_sha256(&runtime_document)?;
    let provenance_document = json!({
        "schema_version": 1,
        "status": "complete",
        "automation_consumption": true,
        "target_id": "parakeet-tdt_ctc-0.6b-ja",
        "upstream": {
            "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
            "revision": "provider-probe-synthetic-v1"
        },
        "development_repo": {
            "repo_id": "generated/provider-probe",
            "revision": "synthetic-v1"
        },
        "assets": [{
            "path": "generated/provider-probe/model.onnx",
            "kind": "onnx",
            "sha256": artifact_sha256,
            "origin": {
                "repo_id": "generated/provider-probe",
                "revision": "synthetic-v1",
                "path": "generated/provider-probe/model.onnx"
            },
            "license": "generated-test-artifact",
            "attribution": "Synthetic provider probe fixture",
            "transformation": {
                "kind": "generated",
                "tool": "e2e-provider-ctc.py",
                "version": "synthetic-v1",
                "input_sha256": null,
                "output_sha256": artifact_sha256
            },
            "candidate": {
                "path": "model.onnx",
                "sha256": artifact_sha256,
                "role": "primary"
            }
        }],
        "blockers": []
    });
    let provenance_document_hash = canonical_sha256(&provenance_document)?;
    let mut bundle = Sha256::new();
    for hash in [
        &reference_hash,
        &evaluation_hash,
        &datasets_hash,
        &runtime_hash,
    ] {
        bundle.update(hash.as_bytes());
    }
    let bundle_sha256 = format!("{:x}", bundle.finalize());

    Ok(json!({
        "config_version": "config-000000",
        "bundle_sha256": bundle_sha256,
        "runtime": {
            "document_sha256": runtime_hash,
            "catalog": runtime_document["catalog"].clone(),
            "profile_set": profile_set
        },
        "reference": {
            "document_sha256": reference_hash,
            "development_artifact": reference_document["development_artifact"].clone(),
            "upstream": reference_document["upstream"].clone(),
            "tokenizer": reference_document["tokenizer"].clone(),
            "reference_id": "provider-probe-reference",
            "reference_revision": "synthetic-v1",
            "canonical_framework": "generated"
        },
        "evaluation_schema": {
            "document_sha256": evaluation_hash,
            "schema_id": "provider-probe-smoke",
            "schema_revision": "synthetic-v1"
        },
        "datasets": {
            "document_sha256": datasets_hash,
            "entries": []
        },
        "provenance": {
            "document_sha256": provenance_document_hash,
            "manifest_sha256": provenance_document_hash,
            "status": "complete",
            "automation_consumption": true,
            "target_id": "parakeet-tdt_ctc-0.6b-ja"
        }
    }))
}

fn canonical_sha256(value: &Value) -> Result<String, String> {
    let bytes = serde_json::to_vec(value).map_err(|error| error.to_string())?;
    let digest = Sha256::digest(bytes);
    Ok(format!("{digest:x}"))
}
