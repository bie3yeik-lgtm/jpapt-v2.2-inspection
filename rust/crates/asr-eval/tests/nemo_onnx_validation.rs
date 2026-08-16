use std::fs;
use std::path::{Path, PathBuf};

use asr_eval::nemo_onnx::{RequiredScope, validate_report};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use uuid::Uuid;

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn write_artifact(root: &Path, relative: &str, bytes: &[u8]) -> Value {
    let path = root.join(relative);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(&path, bytes).unwrap();
    json!({
        "path": relative,
        "sha256": sha256(bytes),
        "size_bytes": bytes.len()
    })
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!("asr-eval-nemo-validation-{}", Uuid::new_v4()));
    fs::create_dir_all(&root).unwrap();
    root
}

fn obstacles() -> Value {
    let ids = [
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
    Value::Array(
        ids.into_iter()
            .map(|id| {
                json!({
                    "id": id,
                    "status": "passed",
                    "evidence": format!("fixture evidence for {id}")
                })
            })
            .collect(),
    )
}

fn report(root: &Path) -> Value {
    let primary = write_artifact(root, "ctc/model.onnx", b"fake canonical fp32 onnx");
    let external = write_artifact(root, "ctc/model.onnx.data", b"fake external weights");
    let tokenizer = write_artifact(root, "tokenizer/tokenizer.model", b"fake sentencepiece");
    let fixture = write_artifact(root, "fixtures/ctc-reference.npz", b"fake reference fixture");

    json!({
        "schema_version": 1,
        "profile_id": "parakeet-nemo-onnx-v1",
        "source": {
            "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
            "revision_requested": "main",
            "revision_resolved": "0123456789abcdef0123456789abcdef01234567",
            "library": "nemo",
            "language": "ja",
            "license": "cc-by-4.0",
            "datasets": ["reazon-research/reazonspeech"],
            "model_file": "parakeet-tdt_ctc-0.6b-ja.nemo",
            "model_file_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        },
        "environment": {
            "python": "3.12.0",
            "nemo": "2.0.0",
            "torch": "2.8.0",
            "onnx": "1.18.0",
            "onnxruntime": "1.22.0",
            "opset": 18,
            "exporter": "nemo_export",
            "dynamo": false
        },
        "resolved_model": {
            "architecture": "hybrid_fastconformer_tdt_ctc",
            "supported_decoders": ["ctc", "tdt"],
            "default_decoder": "tdt",
            "sample_rate_hz": 16000,
            "n_mels": 80,
            "normalize": "per_feature",
            "dither": 0.00001,
            "xscaling": true,
            "tokenizer_type": "sentencepiece",
            "vocab_size": 3072,
            "ctc_blank_id": 3072,
            "tdt_durations": [0, 1, 2, 3, 4]
        },
        "frontend": {
            "location": "outside_onnx",
            "fixture_dither": 0.0,
            "feature_shape_verified": true,
            "parity": {
                "max_abs": 0.0,
                "mean_abs": 0.0,
                "relative_l2": 0.0
            }
        },
        "artifacts": [
            {
                "role": "primary",
                "path": primary["path"],
                "sha256": primary["sha256"],
                "size_bytes": primary["size_bytes"],
                "format": "onnx",
                "precision": "fp32",
                "external_data": [{
                    "path": external["path"],
                    "sha256": external["sha256"],
                    "size_bytes": external["size_bytes"]
                }]
            },
            {
                "role": "tokenizer",
                "path": tokenizer["path"],
                "sha256": tokenizer["sha256"],
                "size_bytes": tokenizer["size_bytes"],
                "format": "sentencepiece",
                "precision": "metadata",
                "external_data": []
            },
            {
                "role": "fixture",
                "path": fixture["path"],
                "sha256": fixture["sha256"],
                "size_bytes": fixture["size_bytes"],
                "format": "npz",
                "precision": "fp32",
                "external_data": []
            }
        ],
        "gates": {
            "source_manifest": {"status": "passed", "evidence": "immutable source resolved"},
            "nemo_load": {"status": "passed", "evidence": "reference checkpoint loaded"},
            "frontend_fixture": {"status": "passed", "evidence": "feature fixture generated"},
            "ctc_export": {"status": "passed", "evidence": "canonical FP32 graph exported"},
            "ctc_onnx_check": {"status": "passed", "evidence": "onnx checker passed"},
            "ctc_ort_cpu": {"status": "passed", "evidence": "ORT CPU session executed"},
            "ctc_reference_parity": {"status": "passed", "evidence": "reference parity passed"},
            "tdt_export": {"status": "not_run", "evidence": "CTC-first fixture"},
            "predictor_state_parity": {"status": "not_run", "evidence": "CTC-first fixture"},
            "joint_parity": {"status": "not_run", "evidence": "CTC-first fixture"},
            "tdt_single_step_parity": {"status": "not_run", "evidence": "CTC-first fixture"},
            "tdt_state_trace_parity": {"status": "not_run", "evidence": "CTC-first fixture"}
        },
        "obstacles": obstacles()
    })
}

#[test]
fn accepts_complete_ctc_bundle_and_rejects_tdt_scope() {
    let root = temp_root();
    let report_path = root.join("nemo-onnx-validation.json");
    fs::write(&report_path, serde_json::to_vec_pretty(&report(&root)).unwrap()).unwrap();

    validate_report(&report_path, &root, RequiredScope::Ctc).unwrap();
    assert!(validate_report(&report_path, &root, RequiredScope::Tdt).is_err());

    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_artifact_tampering() {
    let root = temp_root();
    let report_path = root.join("nemo-onnx-validation.json");
    fs::write(&report_path, serde_json::to_vec_pretty(&report(&root)).unwrap()).unwrap();
    fs::write(root.join("ctc/model.onnx"), b"tampered").unwrap();

    assert!(validate_report(&report_path, &root, RequiredScope::Ctc).is_err());

    fs::remove_dir_all(root).unwrap();
}
