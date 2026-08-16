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
    })
    .expect("target must resolve");

    assert_eq!(resolved.target_id, "parakeet-tdt_ctc-0.6b-ja");
    assert_eq!(resolved.hf_bucket, "gawohok7/jpapt-v2.2-dev-bucket");
    assert_eq!(resolved.hf_model_repo, "gawohok7/jpapt-v2.2-dev");
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
fn source_controlled_bucket_selects_target() {
    let resolved = resolve_target(&ResolveTargetOptions {
        repository_root: repository_root(),
        selector: TargetSelector::Bucket("gawohok7/jpapt-v2.2-dev-bucket".into()),
        runtime_variant: Some("tdt".into()),
    })
    .expect("bucket must resolve from source-controlled targets");

    assert_eq!(resolved.target_id, "parakeet-tdt_ctc-0.6b-ja");
    assert_eq!(resolved.runtime_variant, "tdt");
    assert_eq!(resolved.runtime_profile, "tdt-v1");
    assert_eq!(resolved.decoder, "tdt");
}

#[test]
fn bucket_uri_is_normalized_for_selection() {
    let resolved = resolve_target(&ResolveTargetOptions {
        repository_root: repository_root(),
        selector: TargetSelector::Bucket("hf://buckets/gawohok7/jpapt-v2.2-dev-bucket/".into()),
        runtime_variant: None,
    })
    .expect("bucket URI must resolve");

    assert_eq!(resolved.target_id, "parakeet-tdt_ctc-0.6b-ja");
}

#[test]
fn resolves_whisper_framework_and_profile() {
    let resolved = resolve_target(&ResolveTargetOptions {
        repository_root: repository_root(),
        selector: TargetSelector::Id("kotoba-whisper-v1.0".into()),
        runtime_variant: None,
    })
    .expect("target must resolve");

    assert_eq!(resolved.expected_framework, "transformers");
    assert_eq!(
        resolved.expected_upstream_repo_id,
        "kotoba-tech/kotoba-whisper-v1.0"
    );
    assert_eq!(resolved.runtime_variant, "whisper");
    assert_eq!(resolved.runtime_profile, "whisper-autoregressive-v1");
    assert_eq!(resolved.decoder, "whisper_autoregressive");
}

#[test]
fn unknown_bucket_is_rejected() {
    let error = resolve_target(&ResolveTargetOptions {
        repository_root: repository_root(),
        selector: TargetSelector::Bucket("gawohok7/not-configured-bucket".into()),
        runtime_variant: None,
    })
    .expect_err("unknown bucket must fail");
    assert!(
        error
            .to_string()
            .contains("is not assigned by config/hf-targets")
    );
}
