use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

const REPO_ID: &str = "nvidia/parakeet-tdt_ctc-0.6b-ja";
const PROFILE_ID: &str = "parakeet-nemo-onnx-v1";
const MODEL_FILE: &str = "parakeet-tdt_ctc-0.6b-ja.nemo";
const REQUIRED_OBSTACLES: [&str; 15] = [
    "A-01-dynamo-dynamic-shapes",
    "A-02-nemo-pytorch-exporter-generation",
    "B-01-complex-stft-externalized",
    "B-02-mel-count-from-upstream",
    "B-03-feature-parity",
    "B-04-dither-determinism",
    "C-01-xscaling-from-upstream",
    "C-02-optimization-numeric-drift",
    "D-01-ctc-blank-from-upstream",
    "E-01-predictor-state-shape",
    "F-01-duration-zero-loop-guard",
    "G-01-tokenizer-revision-lock",
    "I-01-ort-session-load",
    "K-01-external-data-complete",
    "K-02-artifact-sha256-complete",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RequiredScope {
    Ctc,
    Tdt,
}

impl RequiredScope {
    pub fn parse(value: &str) -> Result<Self> {
        match value {
            "ctc" => Ok(Self::Ctc),
            "tdt" => Ok(Self::Tdt),
            _ => anyhow::bail!("--require must be exactly ctc or tdt"),
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ValidationReport {
    schema_version: u32,
    profile_id: String,
    source: Source,
    environment: Environment,
    resolved_model: ResolvedModel,
    frontend: Frontend,
    artifacts: Vec<Artifact>,
    gates: Gates,
    obstacles: Vec<Obstacle>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Source {
    repo_id: String,
    revision_requested: String,
    revision_resolved: String,
    library: String,
    language: String,
    license: String,
    datasets: Vec<String>,
    model_file: String,
    model_file_sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Environment {
    python: String,
    nemo: String,
    torch: String,
    onnx: String,
    onnxruntime: String,
    opset: u32,
    exporter: String,
    dynamo: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResolvedModel {
    architecture: String,
    supported_decoders: Vec<String>,
    default_decoder: String,
    sample_rate_hz: u32,
    n_mels: u32,
    normalize: String,
    dither: f64,
    xscaling: bool,
    tokenizer_type: String,
    vocab_size: u32,
    ctc_blank_id: u32,
    tdt_durations: Vec<u32>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Frontend {
    location: String,
    fixture_dither: f64,
    feature_shape_verified: bool,
    parity: Parity,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Parity {
    max_abs: f64,
    mean_abs: f64,
    relative_l2: f64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Artifact {
    role: String,
    path: String,
    sha256: String,
    size_bytes: u64,
    format: String,
    precision: String,
    external_data: Vec<ExternalData>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ExternalData {
    path: String,
    sha256: String,
    size_bytes: u64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Gate {
    status: String,
    evidence: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Gates {
    source_manifest: Gate,
    nemo_load: Gate,
    frontend_fixture: Gate,
    ctc_export: Gate,
    ctc_onnx_check: Gate,
    ctc_ort_cpu: Gate,
    ctc_reference_parity: Gate,
    tdt_export: Gate,
    predictor_state_parity: Gate,
    joint_parity: Gate,
    tdt_single_step_parity: Gate,
    tdt_state_trace_parity: Gate,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Obstacle {
    id: String,
    status: String,
    evidence: String,
}

fn reject_nulls(value: &Value, path: &str) -> Result<()> {
    match value {
        Value::Null => anyhow::bail!("null is forbidden at {path}"),
        Value::Array(values) => {
            for (index, item) in values.iter().enumerate() {
                reject_nulls(item, &format!("{path}[{index}]"))?;
            }
        }
        Value::Object(values) => {
            for (key, item) in values {
                reject_nulls(item, &format!("{path}.{key}"))?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn nonempty(name: &str, value: &str) -> Result<()> {
    ensure!(!value.trim().is_empty(), "{name} must not be empty");
    ensure!(value == value.trim(), "{name} has surrounding whitespace");
    Ok(())
}

fn valid_sha(name: &str, value: &str) -> Result<()> {
    ensure!(value.len() == 64, "{name} must be a 64-character SHA256");
    ensure!(
        value
            .chars()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()),
        "{name} must be lowercase hexadecimal"
    );
    Ok(())
}

fn safe_relative_path(name: &str, value: &str) -> Result<PathBuf> {
    nonempty(name, value)?;
    let path = Path::new(value);
    ensure!(!path.is_absolute(), "{name} must be relative: {value}");
    ensure!(
        !value.contains('\\'),
        "{name} must use forward slashes: {value}"
    );
    ensure!(
        path.components()
            .all(|component| matches!(component, std::path::Component::Normal(_))),
        "unsafe {name}: {value}"
    );
    Ok(path.to_path_buf())
}

fn sha256(path: &Path) -> Result<String> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn verify_file(
    root: &Path,
    label: &str,
    path: &str,
    expected_sha: &str,
    expected_size: u64,
) -> Result<()> {
    valid_sha(&format!("{label}.sha256"), expected_sha)?;
    ensure!(expected_size > 0, "{label}.size_bytes must be > 0");
    let relative = safe_relative_path(&format!("{label}.path"), path)?;
    let root = root
        .canonicalize()
        .context("failed to canonicalize bundle root")?;
    let full = root.join(relative);
    ensure!(full.is_file(), "{label} file missing: {}", full.display());
    let canonical = full.canonicalize()?;
    ensure!(
        canonical.starts_with(&root),
        "{label} escapes bundle root: {}",
        canonical.display()
    );
    let metadata = fs::metadata(&canonical)?;
    ensure!(
        metadata.len() == expected_size,
        "{label} size mismatch: expected={expected_size}, observed={}",
        metadata.len()
    );
    ensure!(
        sha256(&canonical)? == expected_sha,
        "{label} SHA256 mismatch"
    );
    Ok(())
}

fn require_gate(name: &str, gate: &Gate) -> Result<()> {
    nonempty(&format!("gate {name} evidence"), &gate.evidence)?;
    ensure!(
        gate.status == "passed",
        "required gate {name} is not passed: {}",
        gate.status
    );
    Ok(())
}

fn validate_obstacles(report: &ValidationReport, scope: RequiredScope) -> Result<()> {
    let required: BTreeSet<_> = REQUIRED_OBSTACLES.into_iter().collect();
    let mut observed = BTreeMap::new();
    for obstacle in &report.obstacles {
        nonempty("obstacle.id", &obstacle.id)?;
        nonempty("obstacle.evidence", &obstacle.evidence)?;
        ensure!(
            matches!(
                obstacle.status.as_str(),
                "passed" | "failed" | "not_applicable"
            ),
            "invalid obstacle status for {}: {}",
            obstacle.id,
            obstacle.status
        );
        ensure!(
            observed
                .insert(obstacle.id.as_str(), obstacle.status.as_str())
                .is_none(),
            "duplicate obstacle id: {}",
            obstacle.id
        );
    }
    let observed_ids: BTreeSet<_> = observed.keys().copied().collect();
    ensure!(
        observed_ids == required,
        "obstacle set mismatch: expected={required:?}, observed={observed_ids:?}"
    );
    for (id, status) in observed {
        ensure!(status != "failed", "known obstacle check failed: {id}");
        if scope == RequiredScope::Tdt
            && matches!(
                id,
                "E-01-predictor-state-shape" | "F-01-duration-zero-loop-guard"
            )
        {
            ensure!(
                status == "passed",
                "TDT requires obstacle check {id} to pass, not {status}"
            );
        }
    }
    Ok(())
}

fn validate_semantics(report: &ValidationReport) -> Result<()> {
    ensure!(
        report.schema_version == 1,
        "unsupported report schema_version"
    );
    ensure!(report.profile_id == PROFILE_ID, "unexpected profile_id");
    let source = &report.source;
    ensure!(source.repo_id == REPO_ID, "unexpected source repo");
    nonempty("source.revision_requested", &source.revision_requested)?;
    ensure!(
        source.revision_resolved.len() >= 40
            && source
                .revision_resolved
                .chars()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()),
        "source revision must be immutable lowercase hexadecimal"
    );
    ensure!(source.library == "nemo", "source library must be nemo");
    ensure!(source.language == "ja", "source language must be ja");
    ensure!(source.license == "cc-by-4.0", "source license mismatch");
    ensure!(
        source
            .datasets
            .iter()
            .any(|dataset| dataset == "reazon-research/reazonspeech"),
        "Model Card dataset is missing"
    );
    ensure!(
        source.model_file == MODEL_FILE,
        "unexpected source model file"
    );
    valid_sha("source.model_file_sha256", &source.model_file_sha256)?;

    let env = &report.environment;
    for (name, value) in [
        ("python", env.python.as_str()),
        ("nemo", env.nemo.as_str()),
        ("torch", env.torch.as_str()),
        ("onnx", env.onnx.as_str()),
        ("onnxruntime", env.onnxruntime.as_str()),
    ] {
        nonempty(&format!("environment.{name}"), value)?;
    }
    ensure!(env.opset >= 17, "ONNX opset must be >= 17");
    ensure!(
        matches!(
            env.exporter.as_str(),
            "nemo_export" | "torch_onnx_legacy" | "torch_onnx_dynamo"
        ),
        "unsupported exporter"
    );
    if env.exporter == "torch_onnx_dynamo" {
        ensure!(env.dynamo, "torch_onnx_dynamo requires dynamo=true");
    }

    let model = &report.resolved_model;
    ensure!(
        model.architecture == "hybrid_fastconformer_tdt_ctc",
        "architecture mismatch"
    );
    let decoders: BTreeSet<_> = model
        .supported_decoders
        .iter()
        .map(String::as_str)
        .collect();
    ensure!(
        decoders == BTreeSet::from(["ctc", "tdt"]),
        "supported decoders must be exactly ctc+tdt"
    );
    ensure!(
        model.default_decoder == "tdt",
        "Model Card default decoder must be tdt"
    );
    ensure!(
        model.sample_rate_hz == 16000,
        "resolved sample rate must be 16 kHz"
    );
    ensure!(
        model.n_mels > 0,
        "resolved n_mels must come from checkpoint and be > 0"
    );
    nonempty("resolved_model.normalize", &model.normalize)?;
    ensure!(model.dither >= 0.0, "dither cannot be negative");
    let _ = model.xscaling;
    ensure!(
        model.tokenizer_type == "sentencepiece",
        "Model Card tokenizer type must be sentencepiece"
    );
    ensure!(
        model.vocab_size == 3072,
        "Model Card tokenizer vocabulary size must be 3072"
    );
    ensure!(
        model.ctc_blank_id >= model.vocab_size,
        "CTC blank must not collide with tokenizer vocabulary"
    );
    ensure!(
        !model.tdt_durations.is_empty(),
        "TDT durations are required"
    );
    ensure!(
        model.tdt_durations.contains(&0),
        "TDT duration vocabulary must expose duration=0 for loop-safety validation"
    );
    ensure!(
        model.tdt_durations.iter().all(|duration| *duration <= 4),
        "Model Card constrains TDT duration advance to at most 4 encoder frames"
    );

    let frontend = &report.frontend;
    ensure!(
        frontend.location == "outside_onnx",
        "complex STFT frontend must stay outside canonical ONNX graph"
    );
    ensure!(
        frontend.fixture_dither >= 0.0,
        "fixture dither cannot be negative"
    );
    ensure!(
        frontend.feature_shape_verified,
        "frontend feature shape is not verified"
    );
    for (name, value) in [
        ("max_abs", frontend.parity.max_abs),
        ("mean_abs", frontend.parity.mean_abs),
        ("relative_l2", frontend.parity.relative_l2),
    ] {
        ensure!(
            value.is_finite() && value >= 0.0,
            "frontend parity {name} must be finite and non-negative"
        );
    }
    Ok(())
}

fn validate_artifacts(report: &ValidationReport, root: &Path, scope: RequiredScope) -> Result<()> {
    ensure!(!report.artifacts.is_empty(), "artifact list is empty");
    let mut paths = BTreeSet::new();
    let mut roles = BTreeSet::new();
    for artifact in &report.artifacts {
        ensure!(
            matches!(
                artifact.role.as_str(),
                "primary" | "encoder" | "predictor" | "joint" | "tokenizer" | "fixture"
            ),
            "unsupported artifact role: {}",
            artifact.role
        );
        ensure!(
            matches!(
                artifact.format.as_str(),
                "onnx" | "sentencepiece" | "json" | "npy" | "npz"
            ),
            "unsupported artifact format: {}",
            artifact.format
        );
        ensure!(
            matches!(artifact.precision.as_str(), "fp32" | "int8" | "metadata"),
            "unsupported artifact precision: {}",
            artifact.precision
        );
        ensure!(
            paths.insert(artifact.path.as_str()),
            "duplicate artifact path: {}",
            artifact.path
        );
        if artifact.role != "fixture" {
            ensure!(
                roles.insert(artifact.role.as_str()),
                "duplicate artifact role: {}",
                artifact.role
            );
        }
        verify_file(
            root,
            &format!("artifact {}", artifact.role),
            &artifact.path,
            &artifact.sha256,
            artifact.size_bytes,
        )?;
        let mut external_paths = BTreeSet::new();
        for external in &artifact.external_data {
            ensure!(
                external_paths.insert(external.path.as_str()),
                "duplicate external data path for {}",
                artifact.path
            );
            verify_file(
                root,
                &format!("external data for {}", artifact.path),
                &external.path,
                &external.sha256,
                external.size_bytes,
            )?;
        }
    }
    ensure!(
        roles.contains("primary"),
        "CTC primary ONNX artifact is required"
    );
    ensure!(
        roles.contains("tokenizer"),
        "revision-locked tokenizer artifact is required"
    );
    ensure!(
        report
            .artifacts
            .iter()
            .any(|artifact| artifact.role == "fixture"),
        "at least one reference fixture is required"
    );
    if scope == RequiredScope::Tdt {
        for role in ["encoder", "predictor", "joint"] {
            ensure!(roles.contains(role), "TDT artifact role {role} is required");
        }
    }
    Ok(())
}

fn validate_gates(report: &ValidationReport, scope: RequiredScope) -> Result<()> {
    let gates = &report.gates;
    for (name, gate) in [
        ("source_manifest", &gates.source_manifest),
        ("nemo_load", &gates.nemo_load),
        ("frontend_fixture", &gates.frontend_fixture),
        ("ctc_export", &gates.ctc_export),
        ("ctc_onnx_check", &gates.ctc_onnx_check),
        ("ctc_ort_cpu", &gates.ctc_ort_cpu),
        ("ctc_reference_parity", &gates.ctc_reference_parity),
    ] {
        require_gate(name, gate)?;
    }
    if scope == RequiredScope::Tdt {
        for (name, gate) in [
            ("tdt_export", &gates.tdt_export),
            ("predictor_state_parity", &gates.predictor_state_parity),
            ("joint_parity", &gates.joint_parity),
            ("tdt_single_step_parity", &gates.tdt_single_step_parity),
            ("tdt_state_trace_parity", &gates.tdt_state_trace_parity),
        ] {
            require_gate(name, gate)?;
        }
    } else {
        for (name, gate) in [
            ("tdt_export", &gates.tdt_export),
            ("predictor_state_parity", &gates.predictor_state_parity),
            ("joint_parity", &gates.joint_parity),
            ("tdt_single_step_parity", &gates.tdt_single_step_parity),
            ("tdt_state_trace_parity", &gates.tdt_state_trace_parity),
        ] {
            nonempty(&format!("gate {name} evidence"), &gate.evidence)?;
            ensure!(
                matches!(gate.status.as_str(), "passed" | "blocked" | "not_run"),
                "invalid optional TDT gate status for {name}: {}",
                gate.status
            );
        }
    }
    Ok(())
}

pub fn validate_report(
    report_path: &Path,
    bundle_root: &Path,
    scope: RequiredScope,
) -> Result<ValidationReport> {
    let bytes = fs::read(report_path)
        .with_context(|| format!("failed to read {}", report_path.display()))?;
    let value: Value =
        serde_json::from_slice(&bytes).context("NeMo ONNX validation report is not valid JSON")?;
    reject_nulls(&value, "$")?;
    let report: ValidationReport = serde_json::from_value(value)
        .context("NeMo ONNX validation report violates the typed contract")?;
    validate_semantics(&report)?;
    validate_artifacts(&report, bundle_root, scope)?;
    validate_gates(&report, scope)?;
    validate_obstacles(&report, scope)?;
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unknown_scope() {
        assert!(RequiredScope::parse("all").is_err());
    }

    #[test]
    fn rejects_nulls_recursively() {
        assert!(reject_nulls(&serde_json::json!({"x": [1, null]}), "$").is_err());
    }

    #[test]
    fn accepts_safe_relative_paths_only() {
        assert!(safe_relative_path("path", "ctc/model.onnx").is_ok());
        assert!(safe_relative_path("path", "../model.onnx").is_err());
        assert!(safe_relative_path("path", "/tmp/model.onnx").is_err());
    }
}
