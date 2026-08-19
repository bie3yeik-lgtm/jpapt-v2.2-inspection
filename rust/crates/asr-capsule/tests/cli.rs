use std::fs;
use std::process::Command;

use asr_capsule::{CapsuleRow, RecordKind, write_capsule};
use uuid::Uuid;

fn fixture_path() -> std::path::PathBuf {
    std::env::temp_dir().join(format!("jpapt-capsule-cli-{}.parquet", Uuid::new_v4()))
}

fn write_fixture(path: &std::path::Path) {
    let rows = [
        CapsuleRow::new("cli-run", RecordKind::Manifest, 0)
            .unwrap()
            .with_string("name", "run")
            .with_string("category", "evaluation")
            .with_string(
                "metadata_json",
                r#"{"run_context":{"run_id":"cli-run"},"benchmark":{"run_id":"cli-run"}}"#,
            ),
        CapsuleRow::new("cli-run", RecordKind::Sample, 1)
            .unwrap()
            .with_string("sample_id", "sample-1"),
        CapsuleRow::new("cli-run", RecordKind::Metric, 2)
            .unwrap()
            .with_string("metric_name", "quality.cer")
            .with_float64("metric_value", 0.1),
    ];
    write_capsule(path, "cli-run", &rows).unwrap();
}

#[test]
fn validate_reports_operational_counts() {
    let path = fixture_path();
    write_fixture(&path);

    let output = Command::new(env!("CARGO_BIN_EXE_asr-capsule"))
        .args([
            "validate",
            path.to_str().unwrap(),
            "--expected-run-id",
            "cli-run",
        ])
        .output()
        .unwrap();

    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains("run_id=cli-run"));
    assert!(stdout.contains("sample_count=1"));

    fs::remove_file(path).unwrap();
}

#[test]
fn validate_rejects_unexpected_run_id() {
    let path = fixture_path();
    write_fixture(&path);

    let output = Command::new(env!("CARGO_BIN_EXE_asr-capsule"))
        .args([
            "validate",
            path.to_str().unwrap(),
            "--expected-run-id",
            "other-run",
        ])
        .output()
        .unwrap();

    assert!(!output.status.success());
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stderr.contains("does not match expected run_id"));

    fs::remove_file(path).unwrap();
}

#[test]
fn validate_rejects_unexpected_provenance_fingerprint() {
    let path = fixture_path();
    let fingerprint = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    let metadata = serde_json::to_string(&serde_json::json!({
        "run_context":{"run_id":"cli-prov","metadata":{"provenance":{"manifest_sha256":fingerprint}}},
        "benchmark":{"run_id":"cli-prov"}
    })).unwrap();
    let rows = [CapsuleRow::new("cli-prov", RecordKind::Manifest, 0)
        .unwrap()
        .with_string("name", "run")
        .with_string("category", "evaluation")
        .with_string("metadata_json", metadata)];
    write_capsule(&path, "cli-prov", &rows).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_asr-capsule"))
        .args([
            "validate",
            path.to_str().unwrap(),
            "--expected-provenance-manifest-sha256",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ])
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(
        String::from_utf8(output.stderr)
            .unwrap()
            .contains("provenance manifest SHA-256")
    );
    fs::remove_file(path).unwrap();
}
