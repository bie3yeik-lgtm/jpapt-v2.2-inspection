use std::fs;
use std::time::{SystemTime, UNIX_EPOCH};

use asr_hf::allocation::{
    AllocationReadme, collection_prefix, latest_candidate_location, next_sequence_id,
    write_allocation_readme,
};

#[test]
fn allocation_prefixes_are_derived_from_collection() {
    assert_eq!(collection_prefix("candidates").unwrap(), "candidate");
    assert_eq!(collection_prefix("experiments").unwrap(), "experiment");
    assert_eq!(collection_prefix("config").unwrap(), "config");
    assert!(collection_prefix("unknown").is_err());
}

#[test]
fn collection_sequence_is_shared_across_historical_prefixes() {
    let listing = [
        "whisper-export-000001/README.md",
        "whisper-export-000001/encoder.onnx",
        "ctc-export-000004/README.md",
        "cpu-full-eval-000003/README.md",
    ]
    .join("\n");
    assert_eq!(
        next_sequence_id("experiment", &listing).unwrap(),
        "experiment-000005"
    );
}

#[test]
fn historical_directory_advances_canonical_sequence() {
    assert_eq!(
        next_sequence_id("experiment", "structure-example-000001/README.md\n").unwrap(),
        "experiment-000002"
    );
}

#[test]
fn invalid_prefix_and_exhaustion_are_rejected() {
    assert!(next_sequence_id("CPU Full Eval", "").is_err());
    assert!(next_sequence_id("candidate", "anything-999999/README.md\n").is_err());
}

#[test]
fn canonical_candidate_location_has_priority() {
    let listing = [
        "ctc/candidate-000009/metadata.json",
        "tdt/candidate-000010/metadata.json",
        "candidate-000003/metadata.json",
    ]
    .join("\n");
    let location = latest_candidate_location(&listing, Some("ctc")).unwrap();
    assert_eq!(location.id, "candidate-000003");
    assert_eq!(location.relative_path, "candidate-000003");
    assert!(!location.legacy);
}

#[test]
fn legacy_candidate_location_is_read_only_variant_fallback() {
    let listing = [
        "ctc/candidate-000001/metadata.json",
        "tdt/candidate-000004/metadata.json",
        "ctc/candidate-000003/metadata.json",
    ]
    .join("\n");
    let location = latest_candidate_location(&listing, Some("ctc")).unwrap();
    assert_eq!(location.id, "candidate-000003");
    assert_eq!(location.relative_path, "ctc/candidate-000003");
    assert!(location.legacy);
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
        &AllocationReadme {
            allocation_id: "experiment-000042",
            collection: "experiments",
            bucket: "owner/bucket",
            prefix: "experiment",
            sequence: "000042",
            allocated_at: "2026-08-17T00:00:00Z",
            metadata_json: r#"{"zeta":"last","alpha":"first"}"#,
        },
    )
    .unwrap();
    let text = fs::read_to_string(&path).unwrap();
    assert!(text.contains("# experiment-000042"));
    assert!(text.find("- alpha: `first`").unwrap() < text.find("- zeta: `last`").unwrap());
    fs::remove_file(path).unwrap();
}
