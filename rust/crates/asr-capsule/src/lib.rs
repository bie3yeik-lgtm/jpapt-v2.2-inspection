pub mod error;
pub mod model;
pub mod reader;
pub mod schema;
pub mod writer;

pub use error::{CapsuleError, Result};
pub use model::{
    CapsuleRow, CapsuleSummary, CapsuleValue, DEFAULT_ROW_GROUP_SIZE,
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
        std::env::temp_dir().join(format!(
            "jpapt-asr-capsule-{}.parquet",
            Uuid::new_v4()
        ))
    }

    #[test]
    fn schema_matches_python_v1_width() {
        let schema = experiment_capsule_v1_schema();
        assert_eq!(schema.fields().len(), 54);
        assert_eq!(schema.field(0).name(), "schema_version");
        assert_eq!(schema.field(53).name(), "payload");
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

        write_capsule(&path, "run-rust", &[manifest, metric, diagnostic]).unwrap();
        let summary = read_capsule_summary(&path).unwrap();

        assert_eq!(summary.run_id, "run-rust");
        assert_eq!(summary.row_count, 3);
        assert_eq!(summary.sample_count, 0);
        assert_eq!(summary.diagnostic_count, 1);
        assert_eq!(summary.metric("quality.cer"), Some(0.05));

        fs::remove_file(path).unwrap();
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
