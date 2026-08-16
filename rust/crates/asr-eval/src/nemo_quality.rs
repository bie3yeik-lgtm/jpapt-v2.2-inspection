use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::PathBuf;

use asr_metrics::{character_error_rate, normalize_text, word_error_rate};
use asr_runtime::ProviderKind;
use serde::Deserialize;
use serde_json::Value;

use crate::evaluator::{EvaluateOptions, evaluate};
use crate::writer::{ensure_dir, write_json, write_jsonl};
use crate::{EvalError, Result};

const REPO_ID: &str = "nvidia/parakeet-tdt_ctc-0.6b-ja";
const MODEL_FILE: &str = "parakeet-tdt_ctc-0.6b-ja.nemo";
const NORMALIZATION_ID: &str = "asr_metrics_v1";

#[derive(Debug, Clone)]
pub struct NemoOnnxQualityOptions {
    pub provider: ProviderKind,
    pub candidate_contract: PathBuf,
    pub run_context: PathBuf,
    pub resolved_manifest: PathBuf,
    pub nemo_reference: PathBuf,
    pub output: PathBuf,
    pub max_cer_regression: f64,
    pub max_wer_regression: f64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NemoReferenceDocument {
    schema_version: u32,
    reference_run_id: String,
    source: NemoSource,
    decoder: String,
    normalization: String,
    samples: Vec<NemoReferenceSample>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NemoSource {
    repo_id: String,
    revision_resolved: String,
    model_file: String,
    model_file_sha256: String,
    library: String,
    language: String,
    license: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NemoReferenceSample {
    id: String,
    audio_sha256: String,
    reference_text: String,
    text: String,
    normalized_text: String,
}

fn invalid(message: impl Into<String>) -> EvalError {
    EvalError::InvalidInput(message.into())
}

fn reject_nulls(value: &Value, path: &str) -> Result<()> {
    match value {
        Value::Null => return Err(invalid(format!("null is forbidden at {path}"))),
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

fn require_nonempty(name: &str, value: &str) -> Result<()> {
    if value.trim().is_empty() || value != value.trim() {
        return Err(invalid(format!("{name} must be non-empty and trimmed")));
    }
    Ok(())
}

fn require_lower_hex(name: &str, value: &str, min_len: usize, max_len: usize) -> Result<()> {
    if value.len() < min_len
        || value.len() > max_len
        || !value
            .chars()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
    {
        return Err(invalid(format!("{name} must be lowercase hexadecimal")));
    }
    Ok(())
}

fn load_reference(path: &PathBuf) -> Result<NemoReferenceDocument> {
    let raw = fs::read_to_string(path)?;
    let value: Value = serde_json::from_str(&raw)?;
    reject_nulls(&value, "$")?;
    let doc: NemoReferenceDocument = serde_json::from_value(value)?;
    validate_reference(&doc)?;
    Ok(doc)
}

fn validate_reference(doc: &NemoReferenceDocument) -> Result<()> {
    if doc.schema_version != 1 {
        return Err(invalid("NeMo reference schema_version must be 1"));
    }
    require_nonempty("reference_run_id", &doc.reference_run_id)?;
    if doc.source.repo_id != REPO_ID {
        return Err(invalid("unexpected NeMo source repo"));
    }
    require_lower_hex("source.revision_resolved", &doc.source.revision_resolved, 40, 64)?;
    if doc.source.model_file != MODEL_FILE {
        return Err(invalid("unexpected NeMo model file"));
    }
    require_lower_hex("source.model_file_sha256", &doc.source.model_file_sha256, 64, 64)?;
    if doc.source.library != "nemo"
        || doc.source.language != "ja"
        || doc.source.license != "cc-by-4.0"
    {
        return Err(invalid("NeMo source metadata does not match Model Card contract"));
    }
    if doc.decoder != "ctc" {
        return Err(invalid(
            "ASR quality comparison currently requires a CTC NeMo reference; TDT runtime quality comparison is not implemented",
        ));
    }
    if doc.normalization != NORMALIZATION_ID {
        return Err(invalid("unsupported normalization contract"));
    }
    if doc.samples.is_empty() {
        return Err(invalid("NeMo reference sample set must not be empty"));
    }

    let mut ids = BTreeSet::new();
    for sample in &doc.samples {
        require_nonempty("sample.id", &sample.id)?;
        require_lower_hex("sample.audio_sha256", &sample.audio_sha256, 64, 64)?;
        if !ids.insert(sample.id.as_str()) {
            return Err(invalid(format!("duplicate NeMo reference sample id: {}", sample.id)));
        }
        let normalized = normalize_text(&sample.text);
        if normalized != sample.normalized_text {
            return Err(invalid(format!(
                "NeMo reference normalized_text was not produced by {NORMALIZATION_ID}: {}",
                sample.id
            )));
        }
    }
    Ok(())
}

fn load_jsonl(path: &PathBuf) -> Result<Vec<Value>> {
    let raw = fs::read_to_string(path)?;
    let mut values = Vec::new();
    for (index, line) in raw.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let value: Value = serde_json::from_str(line).map_err(|error| {
            invalid(format!("invalid JSONL at {}:{}: {error}", path.display(), index + 1))
        })?;
        values.push(value);
    }
    Ok(values)
}

fn required_str<'a>(value: &'a Value, path: &[&str], label: &str) -> Result<&'a str> {
    let mut cursor = value;
    for key in path {
        cursor = cursor
            .get(*key)
            .ok_or_else(|| invalid(format!("missing {label}")))?;
    }
    cursor
        .as_str()
        .ok_or_else(|| invalid(format!("{label} must be a string")))
}

pub fn measure_nemo_onnx_quality(options: NemoOnnxQualityOptions) -> Result<Value> {
    for (name, value) in [
        ("max_cer_regression", options.max_cer_regression),
        ("max_wer_regression", options.max_wer_regression),
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(invalid(format!("{name} must be finite and >= 0")));
        }
    }

    let reference = load_reference(&options.nemo_reference)?;
    ensure_dir(&options.output)?;
    let onnx_output = options.output.join("onnx");
    let onnx_metrics = evaluate(EvaluateOptions {
        provider: options.provider,
        candidate_contract: options.candidate_contract.clone(),
        run_context: options.run_context.clone(),
        resolved_manifest: options.resolved_manifest.clone(),
        output: onnx_output.clone(),
    })?;

    if onnx_metrics["acceptance"]["passed"] != Value::Bool(true) {
        return Err(invalid(
            "ONNX evaluation did not complete successfully; quality comparison is not meaningful",
        ));
    }

    let candidate_rows = load_jsonl(&onnx_output.join("samples.jsonl"))?;
    let mut candidate_by_id = BTreeMap::new();
    for row in candidate_rows {
        if row.get("status").and_then(Value::as_str) != Some("success") {
            return Err(invalid("candidate sample contains a failed evaluation"));
        }
        let id = required_str(&row, &["sample", "id"], "candidate sample.id")?.to_owned();
        if candidate_by_id.insert(id.clone(), row).is_some() {
            return Err(invalid(format!("duplicate candidate sample id: {id}")));
        }
    }

    if candidate_by_id.len() != reference.samples.len() {
        return Err(invalid(format!(
            "sample count mismatch: NeMo={} ONNX={}",
            reference.samples.len(),
            candidate_by_id.len()
        )));
    }

    let mut compared = Vec::with_capacity(reference.samples.len());
    let mut nemo_cer_sum = 0.0;
    let mut nemo_wer_sum = 0.0;
    let mut onnx_cer_sum = 0.0;
    let mut onnx_wer_sum = 0.0;
    let mut text_matches = 0usize;

    for nemo in &reference.samples {
        let onnx = candidate_by_id
            .get(&nemo.id)
            .ok_or_else(|| invalid(format!("ONNX result missing sample {}", nemo.id)))?;
        let onnx_audio_sha = required_str(
            onnx,
            &["sample", "audio_sha256"],
            "candidate sample.audio_sha256",
        )?;
        let onnx_reference_text = required_str(
            onnx,
            &["sample", "reference_text"],
            "candidate sample.reference_text",
        )?;
        if onnx_audio_sha != nemo.audio_sha256 {
            return Err(invalid(format!("audio SHA mismatch for sample {}", nemo.id)));
        }
        if onnx_reference_text != nemo.reference_text {
            return Err(invalid(format!("ground-truth text mismatch for sample {}", nemo.id)));
        }

        let onnx_text = required_str(onnx, &["output", "text"], "candidate output.text")?;
        let onnx_normalized = normalize_text(onnx_text);
        let stored_onnx_normalized = required_str(
            onnx,
            &["output", "normalized_text"],
            "candidate output.normalized_text",
        )?;
        if onnx_normalized != stored_onnx_normalized {
            return Err(invalid(format!(
                "candidate normalized_text violates {NORMALIZATION_ID}: {}",
                nemo.id
            )));
        }

        let nemo_cer = character_error_rate(&nemo.reference_text, &nemo.text);
        let nemo_wer = word_error_rate(&nemo.reference_text, &nemo.text);
        let onnx_cer = character_error_rate(&nemo.reference_text, onnx_text);
        let onnx_wer = word_error_rate(&nemo.reference_text, onnx_text);
        let text_match = nemo.normalized_text == onnx_normalized;
        if text_match {
            text_matches += 1;
        }

        nemo_cer_sum += nemo_cer;
        nemo_wer_sum += nemo_wer;
        onnx_cer_sum += onnx_cer;
        onnx_wer_sum += onnx_wer;

        compared.push(serde_json::json!({
            "schema_version": 1,
            "sample_id": nemo.id,
            "audio_sha256": nemo.audio_sha256,
            "reference_text": nemo.reference_text,
            "nemo": {
                "text": nemo.text,
                "normalized_text": nemo.normalized_text,
                "cer": nemo_cer,
                "wer": nemo_wer
            },
            "onnx": {
                "text": onnx_text,
                "normalized_text": onnx_normalized,
                "cer": onnx_cer,
                "wer": onnx_wer
            },
            "delta": {
                "cer": onnx_cer - nemo_cer,
                "wer": onnx_wer - nemo_wer
            },
            "normalized_text_match": text_match
        }));
    }

    let count = reference.samples.len() as f64;
    let nemo_cer = nemo_cer_sum / count;
    let nemo_wer = nemo_wer_sum / count;
    let onnx_cer = onnx_cer_sum / count;
    let onnx_wer = onnx_wer_sum / count;
    let cer_regression = onnx_cer - nemo_cer;
    let wer_regression = onnx_wer - nemo_wer;
    let cer_passed = cer_regression <= options.max_cer_regression;
    let wer_passed = wer_regression <= options.max_wer_regression;
    let passed = cer_passed && wer_passed;

    let result = serde_json::json!({
        "schema_version": 1,
        "comparison": {
            "reference_run_id": reference.reference_run_id,
            "candidate_run_id": onnx_metrics["run_id"],
            "decoder": "ctc",
            "normalization": NORMALIZATION_ID,
            "sample_count": reference.samples.len()
        },
        "source": {
            "repo_id": reference.source.repo_id,
            "revision_resolved": reference.source.revision_resolved,
            "model_file": reference.source.model_file,
            "model_file_sha256": reference.source.model_file_sha256
        },
        "quality": {
            "nemo": {"cer": nemo_cer, "wer": nemo_wer},
            "onnx": {"cer": onnx_cer, "wer": onnx_wer},
            "regression": {"cer": cer_regression, "wer": wer_regression},
            "normalized_text_match_rate": text_matches as f64 / count
        },
        "thresholds": {
            "max_cer_regression": options.max_cer_regression,
            "max_wer_regression": options.max_wer_regression
        },
        "acceptance": {
            "passed": passed,
            "cer_passed": cer_passed,
            "wer_passed": wer_passed,
            "failed_checks": [
                if cer_passed { "" } else { "cer_regression" },
                if wer_passed { "" } else { "wer_regression" }
            ].into_iter().filter(|value| !value.is_empty()).collect::<Vec<_>>()
        }
    });

    write_jsonl(&options.output.join("quality-samples.jsonl"), &compared)?;
    write_json(&options.output.join("quality-comparison.json"), &result)?;
    Ok(result)
}
