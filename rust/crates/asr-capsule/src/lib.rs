mod hash;
mod model;
mod reader;
mod schema;
mod writer;

pub use hash::sha256_file;
pub use model::{
    ONNX_CAPSULE_SCHEMA_VERSION, OnnxCapsule, OnnxCapsuleManifest, OnnxCapsuleMetric,
    OnnxCapsuleReceipt, OnnxCapsuleSample,
};
pub use reader::read_onnx_capsule;
pub use schema::onnx_capsule_v1_schema;
pub use writer::write_onnx_capsule;

#[cfg(test)]
mod tests {
    use std::{env, fs};

    use super::*;

    fn fixture() -> OnnxCapsule {
        OnnxCapsule {
            manifest: OnnxCapsuleManifest {
                run_id: "run-1".into(),
                model_id: "model".into(),
                source_framework: "transformers".into(),
                source_revision: "0123456789012345678901234567890123456789".into(),
                candidate_id: "candidate-1".into(),
                provider_id: "cpu".into(),
                decoder: "ctc".into(),
                environment_id: "linux".into(),
                evaluation_input_id: "input-1".into(),
                git_commit: "0123456789012345678901234567890123456789".into(),
                runtime_backend: "onnxruntime".into(),
                provider_registered: true,
                provider_execution_proven: Some(true),
                provider_assignment_proven: Some(true),
                fallback_detected: Some(false),
            },
            samples: vec![OnnxCapsuleSample {
                sample_id: "s1".into(), dataset_id: "dataset".into(), dataset_repo_id: "org/dataset".into(),
                dataset_revision: "abcdef".into(),
                audio_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".into(),
                audio_duration_sec: 1.0, sample_rate_hz: 16_000,
                reference_text: "hello".into(), hypothesis_text: "hello".into(), normalized_text: "hello".into(),
                cer: Some(0.0), wer: Some(0.0), audio_decode_ms: Some(1.0), resample_ms: Some(0.0),
                inference_ms: Some(10.0), decoder_ms: Some(1.0), postprocess_ms: Some(0.5), total_ms: 12.5,
                rtf: Some(0.0125), peak_ram_mb: Some(128.0), peak_device_memory_mb: None,
                status: "success".into(), error_code: None, error_stage: None, error_message: None,
            }],
            metrics: vec![OnnxCapsuleMetric { name: "cer".into(), value: 0.0, unit: Some("ratio".into()) }],
        }
    }

    #[test]
    fn onnx_capsule_round_trip_preserves_semantics() {
        let path = env::temp_dir().join(format!("onnx-capsule-{}.parquet", std::process::id()));
        let expected = fixture();
        let receipt = write_onnx_capsule(&path, &expected).unwrap();
        assert_eq!(receipt.sample_count, 1);
        assert_eq!(receipt.metric_count, 1);
        assert_eq!(receipt.sha256.len(), 64);
        let observed = read_onnx_capsule(&path).unwrap();
        fs::remove_file(path).ok();
        assert_eq!(observed, expected);
    }

    #[test]
    fn failed_sample_uses_status_not_nan_sentinels() {
        let mut sample = fixture().samples.remove(0);
        sample.status = "failed".into();
        sample.cer = None;
        sample.wer = None;
        sample.error_code = Some("INFERENCE_FAILED".into());
        sample.error_stage = Some("inference".into());
        sample.error_message = Some("fixture".into());
        assert!(sample.validate().is_ok());
        sample.cer = Some(f64::NAN);
        assert!(sample.validate().is_err());
    }
}
