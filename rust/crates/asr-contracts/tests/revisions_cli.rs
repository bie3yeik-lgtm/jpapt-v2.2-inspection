use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{Value, json};
use sha2::{Digest, Sha256};

fn canonical_sha(value: &Value) -> String {
    format!("{:x}", Sha256::digest(serde_json::to_vec(value).unwrap()))
}

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root must be reachable from the asr-contracts manifest")
}

#[test]
fn validates_revision_bundle_against_repository_catalog() {
    let root = repository_root();
    let catalog_path = root.join("config/asr-catalog.json");
    let catalog: Value = serde_json::from_slice(&fs::read(&catalog_path).unwrap()).unwrap();
    let catalog_sha = canonical_sha(&catalog);
    let catalog_id = catalog["catalog_id"].as_str().unwrap();

    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let parent =
        std::env::temp_dir().join(format!("jpapt-revisions-{}-{unique}", std::process::id()));
    let revisions = parent.join("revisions");
    fs::create_dir_all(&revisions).unwrap();

    let sha = "a".repeat(64);
    fs::write(
        parent.join("resolved.json"),
        serde_json::to_vec(&json!({
            "schema_version":1,
            "config_version":"config-000001",
            "current_version":"config-000001",
            "selection_source":"current"
        }))
        .unwrap(),
    )
    .unwrap();
    fs::write(
        revisions.join("reference.json"),
        serde_json::to_vec(&json!({
            "schema_version":1,
            "development_artifact":{"repo_id":"dev/model","revision":"dev-rev"},
            "upstream":{"repo_id":"up/model","revision":"up-rev"},
            "tokenizer":{"repo_id":"up/model","revision":"tok-rev"},
            "reference":{"id":"reference-v1","revision":"reference-rev","canonical_framework":"nemo"}
        }))
        .unwrap(),
    )
    .unwrap();
    fs::write(
        revisions.join("evaluation-schema.json"),
        serde_json::to_vec(&json!({
            "schema_version":1,
            "schema":{"id":"evaluation-v1","revision":"evaluation-rev"}
        }))
        .unwrap(),
    )
    .unwrap();
    fs::write(
        revisions.join("datasets-lock.json"),
        serde_json::to_vec(&json!({
            "schema_version":1,
            "datasets":[{
                "id":"dataset-1","repo_id":"org/dataset","revision":"dataset-rev",
                "subset":"default","split":"test","sha256":sha,"manifest":"manifest.json"
            }]
        }))
        .unwrap(),
    )
    .unwrap();
    fs::write(
        revisions.join("runtime.json"),
        serde_json::to_vec(&json!({
            "schema_version":1,
            "catalog":{"id":catalog_id,"sha256":catalog_sha},
            "profile_set":"parakeet-tdt-ctc-v1"
        }))
        .unwrap(),
    )
    .unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_asr-contracts"))
        .current_dir(&root)
        .args([
            "validate-revisions",
            "--root",
            revisions.to_str().unwrap(),
            "--expected-development-repo-id",
            "dev/model",
            "--expected-upstream-repo-id",
            "up/model",
            "--expected-tokenizer-repo-id",
            "up/model",
            "--expected-framework",
            "nemo",
            "--expected-profile-set",
            "parakeet-tdt-ctc-v1",
            "--runtime-variant",
            "ctc",
            "--expected-runtime-profile",
            "ctc-v1",
            "--expected-decoder",
            "ctc",
            "--json",
        ])
        .output()
        .unwrap();

    if !output.status.success() {
        panic!(
            "revision validator failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    let snapshot: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(snapshot["config_version"], "config-000001");
    assert_eq!(snapshot["runtime"]["profile_set"], "parakeet-tdt-ctc-v1");
    assert_eq!(snapshot["datasets"]["entries"][0]["id"], "dataset-1");

    fs::remove_dir_all(parent).unwrap();
}
