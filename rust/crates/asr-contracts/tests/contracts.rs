use std::fs;
use std::time::{SystemTime, UNIX_EPOCH};

use asr_contracts::{
    validate_benchmark, validate_run_context, validate_run_directory, validate_sample_result,
};
use serde_json::{Value, json};

const SHA: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

fn candidate() -> Value {
    json!({
        "schema_version":1,
        "candidate_root":"/candidate",
        "candidate_id":"candidate-000001",
        "profile_set":"parakeet-tdt-ctc-v1",
        "variant":"ctc",
        "profile":"ctc-v1",
        "decoder":"ctc",
        "artifact_contract":"ctc-single-graph-v1",
        "catalog":{"id":"asr-runtime-catalog-v1","sha256":SHA},
        "bundle_sha256":SHA,
        "artifacts":{"primary":{"path":"model.onnx","sha256":SHA,"size_bytes":1}},
        "features":{},
        "runtime_contract":{
            "decoder":"ctc",
            "input_kind":"canonical_waveform",
            "io":{"primary":{"input":"audio_signal","length_input":"length","logits_output":"logits"}},
            "decoder_config":{"blank_id":0}
        }
    })
}

fn run_context() -> Value {
    json!({
        "schema_version":2,
        "run_id":"run-1",
        "created_at":"2026-08-16T00:00:00+00:00",
        "config_identity":"model:linux:cpu:smoke",
        "model_id":"model",
        "environment_id":"linux",
        "provider_id":"cpu",
        "evaluation_id":"smoke",
        "artifact":{
            "path":"candidate/model.onnx","sha256":SHA,"size_bytes":1,
            "candidate_id":"candidate-000001","artifact_role":"primary"
        },
        "git":{"repository":"owner/repo","commit":"deadbeef","ref":"refs/heads/main","dirty":false},
        "host":{
            "os":"Linux","architecture":"x86_64","hostname":"runner",
            "python_version":"3.12.0","implementation":"CPython","is_wsl":false,
            "github_runner_os":"Linux","github_runner_arch":"X64",
            "github_run_id":"1","github_run_attempt":"1"
        },
        "runtime":{
            "implementation":"python","backend":"onnxruntime","backend_version":"1.28.0",
            "provider_id":"cpu","provider_ort_name":"CPUExecutionProvider","provider_available":true
        },
        "revisions":{
            "config_version":"config-000001","bundle_sha256":SHA,
            "runtime":{"document_sha256":SHA,"catalog":{"id":"asr-runtime-catalog-v1","sha256":SHA},"profile_set":"parakeet-tdt-ctc-v1"},
            "reference":{
                "document_sha256":SHA,
                "development_artifact":{"repo_id":"dev/model","revision":"dev"},
                "upstream":{"repo_id":"up/model","revision":"up"},
                "tokenizer":{"repo_id":"up/model","revision":"tok"},
                "reference_id":"reference-v1","reference_revision":"ref","canonical_framework":"nemo"
            },
            "evaluation_schema":{"document_sha256":SHA,"schema_id":"eval-v1","schema_revision":"eval"},
            "datasets":{"document_sha256":SHA,"entries":[]},
            "provenance":{"document_sha256":SHA,"manifest_sha256":SHA,"status":"complete","automation_consumption":true,"target_id":"parakeet-tdt_ctc-0.6b-ja"}
        },
        "config":{
            "identity":"model:linux:cpu:smoke",
            "sources":{
                "model":"config/models/model.toml","provider":"config/providers/cpu.toml",
                "environment":"config/environments/linux.toml","evaluation":"config/evaluation/smoke.toml"
            },
            "resolved":{
                "model":{},"provider":{},"environment":{},"evaluation":{},
                "resolved":{"model_id":"model","provider_id":"cpu","environment_id":"linux","evaluation_id":"smoke"}
            }
        },
        "metadata":{"candidate":candidate(),"runtime_variant":"ctc","runtime_profile":"ctc-v1","provenance":{"manifest_sha256":SHA,"status":"complete","automation_consumption":true,"target_id":"parakeet-tdt_ctc-0.6b-ja"}}
    })
}

fn sample() -> Value {
    json!({
        "schema_version":1,"run_id":"run-1",
        "sample":{
            "id":"sample-1","dataset_id":"dataset","dataset_repo_id":"org/dataset",
            "dataset_revision":"revision","subset":null,"split":"test","index":0,
            "audio_sha256":SHA,"audio_duration_sec":1.0,"sample_rate_hz":16000,"reference_text":"参照"
        },
        "execution":{"runtime":"rust","backend":"onnxruntime","provider_id":"cpu","decoder":"ctc","batch_size":1},
        "output":{"text":"認識","normalized_text":"認識","tokens":[1],"token_count":1},
        "quality":{"cer":0.1,"wer":0.2},
        "timing":{
            "load_ms":null,"session_creation_ms":null,"audio_decode_ms":1.0,"resample_ms":0.0,
            "frontend_ms":null,"encoder_ms":null,"decoder_ms":0.1,"postprocess_ms":0.1,
            "inference_ms":10.0,"total_ms":11.2,"rtf":0.0112
        },
        "memory":{"peak_ram_mb":64.0,"peak_device_memory_mb":null},
        "parity":{
            "reference_run_id":null,"text_match":null,"token_match":null,
            "numeric":{
                "frontend":{"compared":false,"passed":null,"max_abs_error":null,"mean_abs_error":null,"relative_l2":null},
                "encoder":{"compared":false,"passed":null,"max_abs_error":null,"mean_abs_error":null,"relative_l2":null},
                "logits":{"compared":false,"passed":null,"max_abs_error":null,"mean_abs_error":null,"relative_l2":null}
            }
        },
        "provider":{
            "requested":"cpu","registered":true,"used":true,"fallback_detected":false,
            "fallback_only":false,"assigned_nodes":null,"fallback_nodes":0
        },
        "status":"success","errors":[]
    })
}

fn benchmark() -> Value {
    json!({
        "schema_version":1,"run_id":"run-1",
        "candidate":{"candidate_id":"candidate-000001","model_id":"model","artifact_sha256":SHA,"artifact_size_bytes":1,"decoder":"ctc"},
        "evaluation":{
            "suite":"smoke","manifest":"evaluation/manifest.json","expected_sample_count":1,
            "reference_revision_sha256":SHA,"evaluation_schema_sha256":SHA,"datasets_lock_sha256":SHA,"revision_bundle_sha256":SHA
        },
        "runtime":{
            "implementation":"rust","backend":"onnxruntime","backend_version":"1.28.0",
            "environment_id":"linux","provider_id":"cpu","provider_ort_name":"CPUExecutionProvider",
            "os":"Linux","architecture":"x86_64"
        },
        "samples":{"expected":1,"attempted":1,"successful":1,"failed":0,"skipped":0,"total_audio_duration_sec":1.0},
        "quality":{"cer":0.1,"wer":0.2},
        "performance":{
            "load_ms":null,"session_creation_ms":1.0,"total_processing_ms":11.2,"rtf":0.0112,
            "per_sample":{"mean_ms":11.2,"median_ms":11.2,"p50_ms":11.2,"p95_ms":11.2,"p99_ms":11.2,"min_ms":11.2,"max_ms":11.2},
            "components":{"audio_decode_ms":1.0,"resample_ms":0.0,"frontend_ms":null,"encoder_ms":null,"decoder_ms":0.1,"postprocess_ms":0.1,"inference_ms":10.0}
        },
        "memory":{"peak_ram_mb":64.0,"peak_device_memory_mb":null},
        "parity":{
            "reference_run_id":null,"text_matches":0,"text_mismatches":0,"token_matches":0,"token_mismatches":0,
            "text_match_rate":null,"token_match_rate":null,
            "numeric":{
                "frontend":{"compared_samples":0,"failed_samples":0,"max_abs_error":null,"max_mean_abs_error":null,"max_relative_l2":null},
                "encoder":{"compared_samples":0,"failed_samples":0,"max_abs_error":null,"max_mean_abs_error":null,"max_relative_l2":null},
                "logits":{"compared_samples":0,"failed_samples":0,"max_abs_error":null,"max_mean_abs_error":null,"max_relative_l2":null}
            }
        },
        "provider":{"requested":"cpu","registered":true,"execution_proven":true,"fallback_detected":false,"fallback_only":false,"assigned_nodes":null,"fallback_nodes":0},
        "acceptance":{"passed":true,"quality_passed":true,"parity_passed":null,"provider_passed":true,"performance_passed":true,"failed_checks":[],"warnings":[]},
        "errors":{"total":0,"fatal":0,"by_code":{}}
    })
}

#[test]
fn validates_current_canonical_contract_shapes() {
    validate_run_context(&run_context()).unwrap();
    validate_sample_result(&sample()).unwrap();
    validate_benchmark(&benchmark()).unwrap();
}

#[test]
fn run_context_rejects_candidate_profile_set_mismatch() {
    let mut value = run_context();
    value["metadata"]["candidate"]["profile_set"] = Value::String("other".into());
    assert!(validate_run_context(&value).is_err());
}

#[test]
fn run_directory_validation_cross_checks_run_and_samples() {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("jpapt-contracts-{}-{unique}", std::process::id()));
    fs::create_dir_all(&dir).unwrap();
    fs::write(
        dir.join("run-context.json"),
        serde_json::to_vec_pretty(&run_context()).unwrap(),
    )
    .unwrap();
    fs::write(
        dir.join("metrics.json"),
        serde_json::to_vec_pretty(&benchmark()).unwrap(),
    )
    .unwrap();
    fs::write(
        dir.join("samples.jsonl"),
        format!("{}\n", serde_json::to_string(&sample()).unwrap()),
    )
    .unwrap();

    let summary = validate_run_directory(&dir).unwrap();
    assert_eq!(summary.run_id, "run-1");
    assert_eq!(summary.sample_count, 1);

    fs::remove_dir_all(dir).unwrap();
}
