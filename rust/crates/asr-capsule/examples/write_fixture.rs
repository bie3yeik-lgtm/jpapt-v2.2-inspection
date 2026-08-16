use std::path::PathBuf;

use asr_capsule::{CapsuleRow, RecordKind, write_capsule};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .ok_or("usage: write_fixture <output.parquet>")?;

    let manifest = CapsuleRow::new("interop-rust-v1", RecordKind::Manifest, 0)?
        .with_string("name", "run")
        .with_string("category", "evaluation")
        .with_string(
            "metadata_json",
            r#"{"run_context":{"run_id":"interop-rust-v1"},"benchmark":{"run_id":"interop-rust-v1","samples":{"attempted":0}}}"#,
        );
    let metric = CapsuleRow::new("interop-rust-v1", RecordKind::Metric, 1)?
        .with_string("metric_name", "quality.cer")
        .with_float64("metric_value", 0.125);
    let diagnostic = CapsuleRow::new("interop-rust-v1", RecordKind::Diagnostic, 2)?
        .with_string("name", "interop-check")
        .with_string("category", "ci")
        .with_string("status", "info")
        .with_string("metadata_json", r#"{"producer":"rust"}"#);

    let receipt = write_capsule(&path, "interop-rust-v1", &[manifest, metric, diagnostic])?;
    println!(
        "{} {} {}",
        receipt.run_id, receipt.sha256, receipt.size_bytes
    );
    Ok(())
}
