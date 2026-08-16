pub mod error;
pub mod json_adapter;
pub mod model;
pub mod reader;
pub mod schema;
pub mod writer;

pub use error::{CapsuleError, Result};
pub use json_adapter::rows_from_evaluation_json;
pub use model::{
    CapsuleReceipt, CapsuleRow, CapsuleSummary, CapsuleValue, DEFAULT_ROW_GROUP_SIZE,
    EXPERIMENT_CAPSULE_SCHEMA_VERSION, RecordKind,
};
pub use reader::read_capsule_summary;
pub use schema::experiment_capsule_v1_schema;
pub use writer::{CAPSULE_WRITER_VERSION, rows_to_record_batch, write_capsule};

#[cfg(test)]
mod tests {
    use std::fs;

    use uuid::Uuid;

    use super::*;

    fn test_path() -> std::path::PathBuf {
        std::env::temp_dir().join(format!("jpapt-asr-capsule-{}.parquet", Uuid::new_v4()))
    }

    #[test]
    fn schema_matches_python_v1_width() {
        let schema = experiment_capsule_v1_schema();
        assert_eq!(schema.fields().len(), 53);
        assert_eq!(schema.field(0).name(), "schema_version");
        assert_eq!(schema.field(52).name(), "payload");
    }

    #[test]
    fn writes_and_reads_capsule_summary() {
        let path = test_path();
        let manifest = CapsuleRow::new("run-rust", RecordKind::Manifest, 0)
            .unwrap()
            .with_string("name", "run")
            .with_string("category", "evaluation")
            .with_string(
                "metadata_json",
                r#"{"run_context":{"run_id":"run-rust"},"benchmark":{"run_id":"run-rust"}}"#,
            );
        let metric = CapsuleRow::new("run-rust", RecordKind::Metric, 1)
            .unwrap()
            .with_string("metric_name", "quality.cer")
            .with_float64("metric_value", 0.05);
        let diagnostic = CapsuleRow::new("run-rust", RecordKind::Diagnostic, 2)
            .unwrap()
            .with_string("name", "provider-fallback")
            .with_string("category", "provider")
            .with_string("status", "warning");

        let receipt = write_capsule(&path, "run-rust", &[manifest, metric, diagnostic]).unwrap();
        let summary = read_capsule_summary(&path).unwrap();

        assert_eq!(receipt.run_id, "run-rust");
        assert_eq!(receipt.path, path);
        assert_eq!(receipt.sha256.len(), 64);
        assert!(receipt.size_bytes > 0);
        assert_eq!(summary.run_id, "run-rust");
        assert_eq!(summary.row_count, 3);
        assert_eq!(summary.sample_count, 0);
        assert_eq!(summary.diagnostic_count, 1);
        assert_eq!(summary.metric("quality.cer"), Some(0.05));

        fs::remove_file(path).unwrap();
    }

    #[test]
    fn adapts_evaluation_json_to_capsule_rows() {
        let run_context = serde_json::json!({"run_id":"run-json"});
        let samples = vec![serde_json::json!({
            "run_id":"run-json",
            "sample":{
                "id":"sample-1","dataset_id":"dataset","dataset_repo_id":"org/dataset",
                "dataset_revision":"revision","subset":null,"split":"test","index":0,
                "audio_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "audio_duration_sec":1.0,"sample_rate_hz":16000,"reference_text":"参照"
            },
            "execution":{"provider_id":"cpu","decoder":"ctc"},
            "output":{"text":"認識","normalized_text":"認識","tokens":[1],"token_count":1},
            "quality":{"cer":0.1,"wer":0.2},
            "timing":{"total_ms":100.0,"rtf":0.1},
            "memory":{"peak_ram_mb":64.0,"peak_device_memory_mb":null},
            "parity":{},"provider":{},"status":"success","errors":[]
        })];
        let benchmark = serde_json::json!({
            "run_id":"run-json",
            "samples":{"attempted":1},
            "quality":{"cer":0.1},
            "provider":{"execution_proven":true}
        });

        let rows = rows_from_evaluation_json(&run_context, &samples, &benchmark).unwrap();
        assert_eq!(rows[0].record_kind, RecordKind::Manifest);
        assert_eq!(rows[1].record_kind, RecordKind::Sample);
        assert!(rows.iter().any(|row| {
            row.record_kind == RecordKind::Metric
                && matches!(row.field("metric_name"), Some(CapsuleValue::String(value)) if value == "quality.cer")
        }));
    }

    #[test]
    fn rejects_cross_run_rows() {
        let path = test_path();
        let row = CapsuleRow::new("other-run", RecordKind::Manifest, 0).unwrap();
        let error = write_capsule(&path, "run-rust", &[row]).unwrap_err();
        assert!(error.to_string().contains("does not match capsule run_id"));
        assert!(!path.exists());
    }
}
