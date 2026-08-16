use std::path::PathBuf;

use asr_hf::{ResolveTargetOptions, TargetSelector, resolve_target};

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

#[test]
fn resolves_parakeet_default_from_source_config() {
    let resolved = resolve_target(&ResolveTargetOptions {
        repository_root: repository_root(),
        selector: TargetSelector::Id("parakeet-tdt_ctc-0.6b-ja".into()),
        runtime_variant: None,
        targets_json: None,
    })
    .expect("target must resolve");

    assert_eq!(resolved.target_id, "parakeet-tdt_ctc-0.6b-ja");
    assert_eq!(
        resolved.expected_upstream_repo_id,
        "nvidia/parakeet-tdt_ctc-0.6b-ja"
    );
    assert_eq!(resolved.expected_framework, "nemo");
    assert_eq!(resolved.profile_set, "parakeet-tdt-ctc-v1");
    assert_eq!(resolved.runtime_variant, "ctc");
    assert_eq!(resolved.runtime_profile, "ctc-v1");
    assert_eq!(resolved.decoder, "ctc");
}

#[test]
fn routing_snapshot_can_select_bucket_and_override_storage() {
    let routes = r#"{
      "parakeet-tdt_ctc-0.6b-ja": {
        "HF_BUCKET": "example/routed-bucket",
        "HF_MODEL_REPO": "example/routed-model"
      }
    }"#;
    let resolved = resolve_target(&ResolveTargetOptions {
        repository_root: repository_root(),
        selector: TargetSelector::Bucket("example/routed-bucket".into()),
        runtime_variant: Some("tdt".into()),
        targets_json: Some(routes.into()),
    })
    .expect("routed target must resolve");

    assert_eq!(resolved.hf_bucket, "example/routed-bucket");
    assert_eq!(resolved.hf_model_repo, "example/routed-model");
    assert_eq!(
        resolved.expected_development_repo_id,
        "example/routed-model"
    );
    assert_eq!(resolved.runtime_variant, "tdt");
    assert_eq!(resolved.runtime_profile, "tdt-v1");
    assert_eq!(resolved.decoder, "tdt");
}

#[test]
fn resolves_whisper_framework_and_profile() {
    let resolved = resolve_target(&ResolveTargetOptions {
        repository_root: repository_root(),
        selector: TargetSelector::Id("kotoba-whisper-v1.0".into()),
        runtime_variant: None,
        targets_json: None,
    })
    .expect("target must resolve");

    assert_eq!(resolved.expected_framework, "transformers");
    assert_eq!(resolved.runtime_variant, "whisper");
    assert_eq!(resolved.runtime_profile, "whisper-autoregressive-v1");
    assert_eq!(resolved.decoder, "whisper_autoregressive");
}
