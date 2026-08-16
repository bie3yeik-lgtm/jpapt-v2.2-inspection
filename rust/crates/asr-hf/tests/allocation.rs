use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use asr_hf::allocation::{
    load_repository_allocation_catalog, next_sequence_id, write_allocation_readme,
};

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

#[test]
fn allocation_catalog_matches_python_canonical_fingerprint() {
    let catalog = load_repository_allocation_catalog(repository_root()).unwrap();
    assert_eq!(catalog.catalog_id, "hf-allocation-catalog-v1");
    assert_eq!(
        catalog.sha256,
        "adfacbb8e9d248d7b6296272c8230390771de917f8bfda01aab83c34d5335a23"
    );
    assert_eq!(catalog.prefix("experiment.rust_eval").unwrap(), "rust-eval");
}

#[test]
fn candidate_prefix_falls_back_to_default() {
    let catalog = load_repository_allocation_catalog(repository_root()).unwrap();
    assert_eq!(
        catalog.candidate_prefix_key("parakeet-tdt-ctc-v1"),
        "candidate.parakeet-tdt-ctc-v1"
    );
    assert_eq!(
        catalog.candidate_prefix_key("unknown-profile-set"),
        "candidate.default"
    );
}

#[test]
fn collection_sequence_is_shared_across_prefixes() {
    let listing = [
        "whisper-export-000001/README.md",
        "whisper-export-000001/encoder.onnx",
        "ctc-export-000004/README.md",
        "cpu-full-eval-000003/README.md",
    ]
    .join("\n");
    assert_eq!(
        next_sequence_id("whisper-export", &listing).unwrap(),
        "whisper-export-000005"
    );
}

#[test]
fn example_allocation_advances_real_sequence() {
    assert_eq!(
        next_sequence_id("cpu-full-eval", "structure-example-000001/README.md\n").unwrap(),
        "cpu-full-eval-000002"
    );
}

#[test]
fn invalid_prefix_and_exhaustion_are_rejected() {
    assert!(next_sequence_id("CPU Full Eval", "").is_err());
    assert!(next_sequence_id("candidate", "anything-999999/README.md\n").is_err());
}

#[test]
fn allocation_readme_is_deterministic_and_metadata_sorted() {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!(
        "jpapt-allocation-readme-{}-{unique}.md",
        std::process::id()
    ));
    write_allocation_readme(
        &path,
        "rust-eval-000042",
        "experiments",
        "owner/bucket",
        "experiment.rust_eval",
        "rust-eval",
        "000042",
        "2026-08-17T00:00:00Z",
        r#"{"zeta":"last","alpha":"first"}"#,
    )
    .unwrap();
    let text = fs::read_to_string(&path).unwrap();
    assert!(text.contains("# rust-eval-000042"));
    assert!(text.find("- alpha: `first`").unwrap() < text.find("- zeta: `last`").unwrap());
    fs::remove_file(path).unwrap();
}
