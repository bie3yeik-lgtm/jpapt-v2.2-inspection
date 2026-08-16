use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

use anyhow::{Context, Result, bail, ensure};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

const EXPECTED_INITIAL_FILES: usize = 8;

#[derive(Debug, Clone)]
pub struct BucketInitOptions {
    pub bucket_id: String,
    pub model_repo: String,
    pub model_revision: String,
    pub expected_task: String,
    pub expected_library: String,
    pub expected_language: String,
    pub expected_license: String,
    pub expected_architecture: String,
    pub profile_set: String,
    pub confirmation: String,
    pub apply: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ModelManifest {
    pub repo_id: String,
    pub revision_requested: String,
    pub revision_resolved: String,
    pub task: String,
    pub library: String,
    pub language: String,
    pub license: String,
    pub architecture: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BucketManifest {
    pub schema_version: u32,
    pub bucket_id: String,
    pub initialized_at: String,
    pub initialized_by: String,
    pub profile_set: String,
    pub source_model: ModelManifest,
}

#[derive(Debug, Clone, Deserialize)]
struct BucketInfo {
    id: String,
    #[serde(default)]
    total_files: u64,
}

#[derive(Debug, Clone, Deserialize)]
struct SyncPlanRecord {
    action: Option<String>,
}

fn validate_hub_id(name: &str, value: &str) -> Result<()> {
    ensure!(!value.trim().is_empty(), "{name} must not be empty");
    ensure!(
        value == value.trim(),
        "{name} must not contain surrounding whitespace"
    );
    ensure!(
        value.matches('/').count() == 1,
        "{name} must use namespace/name form: {value}"
    );
    ensure!(
        !value.contains("..") && !value.contains('\\'),
        "unsafe {name}: {value}"
    );
    let mut parts = value.split('/');
    ensure!(
        parts.next().is_some_and(|part| !part.is_empty()),
        "invalid {name}: {value}"
    );
    ensure!(
        parts.next().is_some_and(|part| !part.is_empty()),
        "invalid {name}: {value}"
    );
    Ok(())
}

fn validate_nonempty(name: &str, value: &str) -> Result<()> {
    ensure!(!value.trim().is_empty(), "{name} must not be empty");
    ensure!(
        value == value.trim(),
        "{name} must not contain surrounding whitespace"
    );
    Ok(())
}

fn run_hf(args: &[&str]) -> Result<Output> {
    let output = Command::new("hf")
        .args(args)
        .env("HF_HUB_DISABLE_UPDATE_CHECK", "1")
        .output()
        .with_context(|| format!("failed to execute hf CLI: hf {}", args.join(" ")))?;
    if !output.status.success() {
        bail!(
            "hf command failed: hf {}\nstdout:\n{}\nstderr:\n{}",
            args.join(" "),
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
    }
    Ok(output)
}

fn json_output(args: &[&str]) -> Result<Value> {
    let output = run_hf(args)?;
    serde_json::from_slice(&output.stdout).with_context(|| {
        format!(
            "hf command did not return valid JSON: hf {}",
            args.join(" ")
        )
    })
}

fn exact_string(value: &Value, key: &str, context: &str) -> Result<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(ToOwned::to_owned)
        .with_context(|| format!("{context}.{key} must be a non-empty string"))
}

fn card_string(value: &Value, key: &str) -> Result<String> {
    let card = value
        .get("cardData")
        .and_then(Value::as_object)
        .context("model manifest cardData must be an object")?;
    card.get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(ToOwned::to_owned)
        .with_context(|| format!("model manifest cardData.{key} must be a non-empty string"))
}

fn card_language(value: &Value) -> Result<String> {
    let raw = value
        .get("cardData")
        .and_then(Value::as_object)
        .and_then(|card| card.get("language"))
        .context("model manifest cardData.language is required")?;
    match raw {
        Value::String(language) if !language.trim().is_empty() => Ok(language.clone()),
        Value::Array(values) if values.len() == 1 => values[0]
            .as_str()
            .filter(|language| !language.trim().is_empty())
            .map(ToOwned::to_owned)
            .context(
                "model manifest cardData.language must contain exactly one non-empty language",
            ),
        _ => bail!(
            "model manifest cardData.language must be one string or a single-element string array"
        ),
    }
}

fn model_architecture(value: &Value) -> Result<String> {
    value
        .get("config")
        .and_then(Value::as_object)
        .and_then(|config| config.get("model_type"))
        .and_then(Value::as_str)
        .filter(|architecture| !architecture.trim().is_empty())
        .map(ToOwned::to_owned)
        .context("model manifest config.model_type is required")
}

fn parse_model_manifest(value: &Value, revision_requested: &str) -> Result<ModelManifest> {
    let manifest = ModelManifest {
        repo_id: exact_string(value, "id", "model manifest")?,
        revision_requested: revision_requested.to_owned(),
        revision_resolved: exact_string(value, "sha", "model manifest")?,
        task: exact_string(value, "pipeline_tag", "model manifest")?,
        library: exact_string(value, "library_name", "model manifest")?,
        language: card_language(value)?,
        license: card_string(value, "license")?,
        architecture: model_architecture(value)?,
    };
    ensure!(
        manifest.revision_resolved.len() >= 40
            && manifest
                .revision_resolved
                .chars()
                .all(|c| c.is_ascii_hexdigit()),
        "model manifest sha is not an immutable hexadecimal revision: {}",
        manifest.revision_resolved
    );
    Ok(manifest)
}

fn fetch_model_manifest(repo: &str, revision: &str) -> Result<ModelManifest> {
    let value = json_output(&[
        "models",
        "info",
        repo,
        "--revision",
        revision,
        "--expand",
        "sha,library_name,pipeline_tag,cardData,config",
        "--format",
        "json",
    ])?;
    parse_model_manifest(&value, revision)
}

fn validate_model_manifest(manifest: &ModelManifest, options: &BucketInitOptions) -> Result<()> {
    let checks = [
        (
            "repo_id",
            manifest.repo_id.as_str(),
            options.model_repo.as_str(),
        ),
        (
            "task",
            manifest.task.as_str(),
            options.expected_task.as_str(),
        ),
        (
            "library",
            manifest.library.as_str(),
            options.expected_library.as_str(),
        ),
        (
            "language",
            manifest.language.as_str(),
            options.expected_language.as_str(),
        ),
        (
            "license",
            manifest.license.as_str(),
            options.expected_license.as_str(),
        ),
        (
            "architecture",
            manifest.architecture.as_str(),
            options.expected_architecture.as_str(),
        ),
    ];
    for (name, observed, expected) in checks {
        ensure!(
            observed == expected,
            "model manifest mismatch for {name}: expected={expected:?}, observed={observed:?}"
        );
    }
    Ok(())
}

fn fetch_bucket_info(bucket_id: &str) -> Result<BucketInfo> {
    let value = json_output(&["buckets", "info", bucket_id])?;
    serde_json::from_value(value).context("failed to decode hf buckets info response")
}

fn require_empty_bucket(bucket_id: &str) -> Result<()> {
    let info = fetch_bucket_info(bucket_id)?;
    ensure!(
        info.id == bucket_id,
        "bucket identity mismatch: requested={bucket_id}, observed={}",
        info.id
    );
    ensure!(
        info.total_files == 0,
        "refusing to initialize non-empty bucket {bucket_id}: total_files={}",
        info.total_files
    );
    Ok(())
}

fn write_text(path: &Path, content: &str) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    fs::write(path, content).with_context(|| format!("failed to write {}", path.display()))
}

fn initialize_staging(root: &Path, manifest: &BucketManifest) -> Result<()> {
    let manifest_json = serde_json::to_string_pretty(manifest)? + "\n";
    write_text(&root.join("bucket-manifest.json"), &manifest_json)?;
    write_text(
        &root.join("README.md"),
        &format!(
            "# {}\n\nInitialized by `asr-eval bucket-init`.\n\n- Source model: `{}`\n- Model revision: `{}`\n- Runtime profile set: `{}`\n- Manifest: `bucket-manifest.json`\n\nThis Bucket is mutable infrastructure. Candidate/config/run immutability is enforced by repository tooling, not by Hugging Face Bucket versioning.\n",
            manifest.bucket_id,
            manifest.source_model.repo_id,
            manifest.source_model.revision_resolved,
            manifest.profile_set,
        ),
    )?;
    for (path, title) in [
        ("config/README.md", "Configuration"),
        (
            "config/versions/README.md",
            "Immutable configuration versions",
        ),
        ("candidates/README.md", "Write-once candidate prefixes"),
        ("experiments/README.md", "Experiment allocation records"),
        ("runs/README.md", "Evaluation runs"),
        ("benchmarks/README.md", "Benchmark summaries"),
    ] {
        write_text(
            &root.join(path),
            &format!(
                "# {title}\n\nManaged by repository workflows. Do not manually allocate numeric IDs or overwrite immutable prefixes.\n"
            ),
        )?;
    }
    Ok(())
}

fn validate_plan(path: &Path) -> Result<usize> {
    let text = fs::read_to_string(path)
        .with_context(|| format!("failed to read sync plan {}", path.display()))?;
    let mut actions = Vec::new();
    for (line_number, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let record: SyncPlanRecord = serde_json::from_str(line)
            .with_context(|| format!("invalid sync plan JSON at line {}", line_number + 1))?;
        if let Some(action) = record.action {
            actions.push(action.to_ascii_lowercase());
        }
    }
    ensure!(!actions.is_empty(), "sync plan contains no file operations");
    let unsafe_actions: BTreeSet<_> = actions
        .iter()
        .filter(|action| action.as_str() != "upload")
        .cloned()
        .collect();
    ensure!(
        unsafe_actions.is_empty(),
        "refusing non-upload sync plan actions: {unsafe_actions:?}"
    );
    ensure!(
        actions.len() == EXPECTED_INITIAL_FILES,
        "unexpected initialization file count: expected={EXPECTED_INITIAL_FILES}, planned={}",
        actions.len()
    );
    Ok(actions.len())
}

fn create_plan(staging: &Path, bucket_id: &str, plan: &Path) -> Result<usize> {
    let remote = format!("hf://buckets/{bucket_id}");
    let staging = staging.to_string_lossy();
    let plan = plan.to_string_lossy();
    run_hf(&["buckets", "sync", &staging, &remote, "--plan", &plan])?;
    validate_plan(Path::new(plan.as_ref()))
}

fn verify_remote_manifest(
    bucket_id: &str,
    expected: &BucketManifest,
    temp_root: &Path,
) -> Result<()> {
    let destination = temp_root.join("remote-bucket-manifest.json");
    let remote = format!("hf://buckets/{bucket_id}/bucket-manifest.json");
    let destination_arg = destination.to_string_lossy();
    run_hf(&["buckets", "cp", &remote, &destination_arg])?;
    let actual: BucketManifest = serde_json::from_slice(&fs::read(&destination)?)?;
    ensure!(
        actual.source_model.revision_resolved == expected.source_model.revision_resolved
            && actual.bucket_id == expected.bucket_id
            && actual.profile_set == expected.profile_set,
        "remote bucket manifest does not match initialized manifest"
    );
    Ok(())
}

pub fn initialize_bucket(options: BucketInitOptions) -> Result<BucketManifest> {
    validate_hub_id("bucket_id", &options.bucket_id)?;
    validate_hub_id("model_repo", &options.model_repo)?;
    for (name, value) in [
        ("model_revision", options.model_revision.as_str()),
        ("expected_task", options.expected_task.as_str()),
        ("expected_library", options.expected_library.as_str()),
        ("expected_language", options.expected_language.as_str()),
        ("expected_license", options.expected_license.as_str()),
        (
            "expected_architecture",
            options.expected_architecture.as_str(),
        ),
        ("profile_set", options.profile_set.as_str()),
    ] {
        validate_nonempty(name, value)?;
    }
    let expected_confirmation = format!("{}:{}", options.bucket_id, options.model_repo);
    ensure!(
        options.confirmation == expected_confirmation,
        "confirmation mismatch; expected exactly {expected_confirmation:?}"
    );
    ensure!(
        std::env::var_os("HF_TOKEN").is_some(),
        "HF_TOKEN is required"
    );

    require_empty_bucket(&options.bucket_id)?;
    let model_manifest = fetch_model_manifest(&options.model_repo, &options.model_revision)?;
    validate_model_manifest(&model_manifest, &options)?;

    let initialized_by = std::env::var("GITHUB_ACTOR").unwrap_or_else(|_| "local".to_string());
    let bucket_manifest = BucketManifest {
        schema_version: 1,
        bucket_id: options.bucket_id.clone(),
        initialized_at: Utc::now().to_rfc3339(),
        initialized_by,
        profile_set: options.profile_set.clone(),
        source_model: model_manifest.clone(),
    };

    let temp_root = std::env::temp_dir().join(format!("asr-eval-bucket-init-{}", Uuid::new_v4()));
    let staging = temp_root.join("staging");
    let plan = temp_root.join("sync-plan.jsonl");
    fs::create_dir_all(&staging)?;
    initialize_staging(&staging, &bucket_manifest)?;
    let planned = create_plan(&staging, &options.bucket_id, &plan)?;
    eprintln!("validated conservative sync plan: {planned} upload operations");

    if options.apply {
        require_empty_bucket(&options.bucket_id)?;
        let revalidated =
            fetch_model_manifest(&options.model_repo, &model_manifest.revision_resolved)?;
        validate_model_manifest(&revalidated, &options)?;
        ensure!(
            revalidated.revision_resolved == model_manifest.revision_resolved,
            "model revision changed between plan and apply"
        );
        let plan_arg = plan.to_string_lossy();
        run_hf(&["buckets", "sync", "--apply", &plan_arg])?;
        let info = fetch_bucket_info(&options.bucket_id)?;
        ensure!(
            info.total_files == EXPECTED_INITIAL_FILES as u64,
            "post-initialization bucket file count mismatch: expected={EXPECTED_INITIAL_FILES}, observed={}",
            info.total_files
        );
        verify_remote_manifest(&options.bucket_id, &bucket_manifest, &temp_root)?;
    }

    let _ = fs::remove_dir_all(&temp_root);
    Ok(bucket_manifest)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn manifest_json() -> Value {
        json!({
            "id": "kotoba-tech/kotoba-whisper-v2.0",
            "sha": "0123456789abcdef0123456789abcdef01234567",
            "library_name": "transformers",
            "pipeline_tag": "automatic-speech-recognition",
            "cardData": {"language": "ja", "license": "apache-2.0"},
            "config": {"model_type": "whisper"}
        })
    }

    #[test]
    fn parses_expected_kotoba_manifest_shape() {
        let manifest = parse_model_manifest(&manifest_json(), "main").unwrap();
        assert_eq!(manifest.repo_id, "kotoba-tech/kotoba-whisper-v2.0");
        assert_eq!(manifest.task, "automatic-speech-recognition");
        assert_eq!(manifest.library, "transformers");
        assert_eq!(manifest.language, "ja");
        assert_eq!(manifest.license, "apache-2.0");
        assert_eq!(manifest.architecture, "whisper");
    }

    #[test]
    fn rejects_multi_language_card_for_single_language_initializer() {
        let mut value = manifest_json();
        value["cardData"]["language"] = json!(["ja", "en"]);
        assert!(parse_model_manifest(&value, "main").is_err());
    }

    #[test]
    fn rejects_unsafe_hub_ids() {
        assert!(validate_hub_id("bucket", "gawohok7/ci-test").is_ok());
        assert!(validate_hub_id("bucket", "gawohok7/../ci-test").is_err());
        assert!(validate_hub_id("bucket", "ci-test").is_err());
    }
}
