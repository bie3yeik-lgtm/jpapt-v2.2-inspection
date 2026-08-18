use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct HfJobMount {
    source: String,
    target: String,
    mode: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct HfJobPlan {
    schema_version: u32,
    job_name: String,
    flavor: String,
    image: String,
    image_digest: String,
    candidate_id: String,
    suite: String,
    environment: String,
    provider: String,
    hf_bucket: String,
    dataset_source: String,
    dataset_id: String,
    dataset_dir: String,
    output_dir: String,
    result_uri: String,
    run_id: u64,
    run_attempt: u64,
    mounts: Vec<HfJobMount>,
    hf_args: Vec<String>,
}

#[derive(Debug)]
struct PlanInput {
    built_image: String,
    image_override: String,
    candidate_id: String,
    suite: String,
    environment: String,
    provider: String,
    hf_bucket: String,
    dataset_source: String,
    dataset_id: String,
    flavor: String,
    run_id: u64,
    run_attempt: u64,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-hf-job: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(usage)?;
    let flags = parse_flags(args.collect())?;
    match command.as_str() {
        "plan" => plan_command(flags),
        "validate" => validate_command(flags),
        "run" => run_command(flags),
        _ => Err(usage()),
    }
}

fn usage() -> String {
    "usage: asr-hf-job plan --built-image REF [--image-override REF] --candidate-id candidate-NNNNNN --suite SUITE --environment linux-cpu|linux-cuda --provider PROVIDER --hf-bucket namespace/name --dataset-source bucket|repository|custom [--dataset-id namespace/name] --flavor FLAVOR --run-id N --run-attempt N --output-json PATH [--github-output PATH] | validate --plan PATH | run --plan PATH".to_owned()
}

fn parse_flags(args: Vec<String>) -> Result<BTreeMap<String, String>, String> {
    let mut result = BTreeMap::new();
    let mut iter = args.into_iter();
    while let Some(flag) = iter.next() {
        if !flag.starts_with("--") {
            return Err(format!("unexpected argument {flag:?}"));
        }
        let value = iter
            .next()
            .ok_or_else(|| format!("{flag} requires a value"))?;
        if result.insert(flag.clone(), value).is_some() {
            return Err(format!("duplicate argument {flag}"));
        }
    }
    Ok(result)
}

fn required(values: &mut BTreeMap<String, String>, name: &str) -> Result<String, String> {
    values
        .remove(name)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{name} is required"))
}

fn optional(values: &mut BTreeMap<String, String>, name: &str) -> String {
    values.remove(name).unwrap_or_default()
}

fn positive_u64(value: String, name: &str) -> Result<u64, String> {
    value
        .parse::<u64>()
        .ok()
        .filter(|value| *value >= 1)
        .ok_or_else(|| format!("{name} must be a positive integer"))
}

fn no_flags(values: BTreeMap<String, String>) -> Result<(), String> {
    if values.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "unsupported arguments: {}",
            values.keys().cloned().collect::<Vec<_>>().join(", ")
        ))
    }
}

fn plan_command(mut flags: BTreeMap<String, String>) -> Result<(), String> {
    let input = PlanInput {
        built_image: required(&mut flags, "--built-image")?,
        image_override: optional(&mut flags, "--image-override"),
        candidate_id: required(&mut flags, "--candidate-id")?,
        suite: required(&mut flags, "--suite")?,
        environment: required(&mut flags, "--environment")?,
        provider: required(&mut flags, "--provider")?,
        hf_bucket: required(&mut flags, "--hf-bucket")?,
        dataset_source: required(&mut flags, "--dataset-source")?,
        dataset_id: optional(&mut flags, "--dataset-id"),
        flavor: required(&mut flags, "--flavor")?,
        run_id: positive_u64(required(&mut flags, "--run-id")?, "--run-id")?,
        run_attempt: positive_u64(
            required(&mut flags, "--run-attempt")?,
            "--run-attempt",
        )?,
    };
    let output_json = PathBuf::from(required(&mut flags, "--output-json")?);
    let github_output = optional(&mut flags, "--github-output");
    no_flags(flags)?;

    let plan = build_plan(input)?;
    validate_plan(&plan)?;
    write_plan(&output_json, &plan)?;
    let digest = plan_sha256(&plan)?;

    if !github_output.is_empty() {
        let text = format!(
            "job_name={}\nimage={}\nimage_digest={}\nresult_uri={}\noutput_dir={}\ndataset_dir={}\nplan_sha256={}\n",
            plan.job_name,
            plan.image,
            plan.image_digest,
            plan.result_uri,
            plan.output_dir,
            plan.dataset_dir,
            digest
        );
        fs::write(&github_output, text)
            .map_err(|error| format!("{github_output}: {error}"))?;
    }

    println!(
        "{}",
        serde_json::to_string(&plan).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn validate_command(mut flags: BTreeMap<String, String>) -> Result<(), String> {
    let plan_path = PathBuf::from(required(&mut flags, "--plan")?);
    no_flags(flags)?;
    let plan = read_plan(&plan_path)?;
    validate_plan(&plan)?;
    println!("{}", plan_sha256(&plan)?);
    Ok(())
}

fn run_command(mut flags: BTreeMap<String, String>) -> Result<(), String> {
    let plan_path = PathBuf::from(required(&mut flags, "--plan")?);
    no_flags(flags)?;
    let plan = read_plan(&plan_path)?;
    validate_plan(&plan)?;
    if env::var("HF_TOKEN")
        .ok()
        .map(|value| value.trim().is_empty())
        .unwrap_or(true)
    {
        return Err("HF_TOKEN is required before invoking Hugging Face Jobs".to_owned());
    }

    eprintln!(
        "[asr-hf-job] invoking hf with validated plan sha256={} argv={}",
        plan_sha256(&plan)?,
        serde_json::to_string(&plan.hf_args).map_err(|error| error.to_string())?
    );
    let status = Command::new("hf")
        .args(&plan.hf_args)
        .status()
        .map_err(|error| format!("failed to execute hf CLI: {error}"))?;
    if !status.success() {
        return Err(format!("hf jobs run failed with status {status}"));
    }
    Ok(())
}

fn build_plan(input: PlanInput) -> Result<HfJobPlan, String> {
    validate_candidate_id(&input.candidate_id)?;
    validate_choice("suite", &input.suite, &["probe", "smoke", "parity"])?;
    validate_choice(
        "dataset_source",
        &input.dataset_source,
        &["bucket", "repository", "custom"],
    )?;
    validate_bucket(&input.hf_bucket)?;
    validate_flavor(&input.flavor)?;

    match (input.environment.as_str(), input.provider.as_str()) {
        ("linux-cpu", "CPUExecutionProvider") => {}
        ("linux-cuda", "CUDAExecutionProvider") => {}
        ("linux-cpu", _) => {
            return Err("linux-cpu HF Jobs requires CPUExecutionProvider".to_owned());
        }
        ("linux-cuda", _) => {
            return Err("linux-cuda HF Jobs requires CUDAExecutionProvider".to_owned());
        }
        _ => return Err("HF Jobs plan only supports linux-cpu or linux-cuda".to_owned()),
    }

    if input.dataset_source == "bucket" {
        if !input.dataset_id.is_empty() {
            return Err("dataset_id must be empty when dataset_source=bucket".to_owned());
        }
    } else {
        validate_repository_id(&input.dataset_id, "dataset_id")?;
    }

    let image = if input.image_override.is_empty() {
        input.built_image
    } else {
        input.image_override
    };
    let image_digest = image_digest(&image)?;

    let suffix = format!("{}-{}-{}", input.suite, input.run_id, input.run_attempt);
    let output_dir = format!(
        "/jpapt-output/runs/hf-jobs/{}/{}",
        input.candidate_id, suffix
    );
    let result_uri = format!(
        "hf://buckets/{}/runs/hf-jobs/{}/{}/result.json",
        input.hf_bucket, input.candidate_id, suffix
    );
    let job_name = format!(
        "jpapt-{}-{}-{}-{}",
        input.candidate_id, input.suite, input.run_id, input.run_attempt
    );
    validate_job_name(&job_name)?;

    let mut mounts = vec![HfJobMount {
        source: format!("hf://buckets/{}", input.hf_bucket),
        target: "/jpapt-output".to_owned(),
        mode: "rw".to_owned(),
    }];
    let dataset_dir = if input.dataset_source == "bucket" {
        "/jpapt-output/datasets".to_owned()
    } else {
        mounts.push(HfJobMount {
            source: format!("hf://datasets/{}", input.dataset_id),
            target: "/data".to_owned(),
            mode: "ro".to_owned(),
        });
        "/data".to_owned()
    };

    let mut plan = HfJobPlan {
        schema_version: SCHEMA_VERSION,
        job_name,
        flavor: input.flavor,
        image,
        image_digest,
        candidate_id: input.candidate_id,
        suite: input.suite,
        environment: input.environment,
        provider: input.provider,
        hf_bucket: input.hf_bucket,
        dataset_source: input.dataset_source,
        dataset_id: input.dataset_id,
        dataset_dir,
        output_dir,
        result_uri,
        run_id: input.run_id,
        run_attempt: input.run_attempt,
        mounts,
        hf_args: Vec::new(),
    };
    plan.hf_args = expected_hf_args(&plan);
    Ok(plan)
}

fn expected_hf_args(plan: &HfJobPlan) -> Vec<String> {
    let mut args = vec![
        "jobs".to_owned(),
        "run".to_owned(),
        "--flavor".to_owned(),
        plan.flavor.clone(),
        "--name".to_owned(),
        plan.job_name.clone(),
    ];
    for mount in &plan.mounts {
        args.push("-v".to_owned());
        args.push(format!("{}:{}:{}", mount.source, mount.target, mount.mode));
    }
    args.extend([
        plan.image.clone(),
        "--suite".to_owned(),
        plan.suite.clone(),
        "--provider".to_owned(),
        plan.provider.clone(),
        "--dataset-dir".to_owned(),
        plan.dataset_dir.clone(),
        "--output".to_owned(),
        format!("{}/result.json", plan.output_dir),
    ]);
    args
}

fn validate_plan(plan: &HfJobPlan) -> Result<(), String> {
    if plan.schema_version != SCHEMA_VERSION {
        return Err(format!(
            "unsupported HF Jobs plan schema_version={}",
            plan.schema_version
        ));
    }
    validate_candidate_id(&plan.candidate_id)?;
    validate_choice("suite", &plan.suite, &["probe", "smoke", "parity"])?;
    validate_choice(
        "dataset_source",
        &plan.dataset_source,
        &["bucket", "repository", "custom"],
    )?;
    validate_bucket(&plan.hf_bucket)?;
    validate_flavor(&plan.flavor)?;
    if plan.image_digest != image_digest(&plan.image)? {
        return Err("image_digest does not match the selected immutable image".to_owned());
    }
    validate_job_name(&plan.job_name)?;
    if plan.run_id == 0 || plan.run_attempt == 0 {
        return Err("run_id and run_attempt must be positive".to_owned());
    }
    match (plan.environment.as_str(), plan.provider.as_str()) {
        ("linux-cpu", "CPUExecutionProvider") | ("linux-cuda", "CUDAExecutionProvider") => {}
        _ => return Err("HF Jobs environment/provider binding is invalid".to_owned()),
    }
    if plan.dataset_source == "bucket" {
        if !plan.dataset_id.is_empty() || plan.dataset_dir != "/jpapt-output/datasets" {
            return Err("bucket dataset routing is inconsistent".to_owned());
        }
        if plan.mounts.len() != 1 {
            return Err("bucket dataset routing must have exactly one mount".to_owned());
        }
    } else {
        validate_repository_id(&plan.dataset_id, "dataset_id")?;
        if plan.dataset_dir != "/data" || plan.mounts.len() != 2 {
            return Err("repository/custom dataset routing is inconsistent".to_owned());
        }
    }

    let expected_output_dir = format!(
        "/jpapt-output/runs/hf-jobs/{}/{}-{}-{}",
        plan.candidate_id, plan.suite, plan.run_id, plan.run_attempt
    );
    if plan.output_dir != expected_output_dir {
        return Err("output_dir does not match canonical HF Jobs layout".to_owned());
    }
    let expected_result_uri = format!(
        "hf://buckets/{}/runs/hf-jobs/{}/{}-{}-{}/result.json",
        plan.hf_bucket, plan.candidate_id, plan.suite, plan.run_id, plan.run_attempt
    );
    if plan.result_uri != expected_result_uri {
        return Err("result_uri does not match canonical HF Jobs layout".to_owned());
    }

    let expected_mounts = if plan.dataset_source == "bucket" {
        vec![HfJobMount {
            source: format!("hf://buckets/{}", plan.hf_bucket),
            target: "/jpapt-output".to_owned(),
            mode: "rw".to_owned(),
        }]
    } else {
        vec![
            HfJobMount {
                source: format!("hf://buckets/{}", plan.hf_bucket),
                target: "/jpapt-output".to_owned(),
                mode: "rw".to_owned(),
            },
            HfJobMount {
                source: format!("hf://datasets/{}", plan.dataset_id),
                target: "/data".to_owned(),
                mode: "ro".to_owned(),
            },
        ]
    };
    if plan.mounts != expected_mounts {
        return Err("mount set does not match canonical HF Jobs routing".to_owned());
    }
    if plan.hf_args != expected_hf_args(plan) {
        return Err("hf_args does not match canonical HF Jobs command".to_owned());
    }
    Ok(())
}

fn validate_choice(name: &str, value: &str, choices: &[&str]) -> Result<(), String> {
    if choices.contains(&value) {
        Ok(())
    } else {
        Err(format!("{name} must be one of {choices:?}; got {value:?}"))
    }
}

fn validate_candidate_id(value: &str) -> Result<(), String> {
    if value.len() == 16
        && value.starts_with("candidate-")
        && value[10..].chars().all(|ch| ch.is_ascii_digit())
    {
        Ok(())
    } else {
        Err("candidate_id must be canonical candidate-NNNNNN".to_owned())
    }
}

fn validate_repository_id(value: &str, field: &str) -> Result<(), String> {
    let mut parts = value.split('/');
    let owner = parts.next().unwrap_or_default();
    let name = parts.next().unwrap_or_default();
    if owner.is_empty() || name.is_empty() || parts.next().is_some() {
        return Err(format!("{field} must use namespace/name"));
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "._-/".contains(ch))
    {
        return Err(format!("{field} contains unsupported characters"));
    }
    Ok(())
}

fn validate_bucket(value: &str) -> Result<(), String> {
    validate_repository_id(value, "hf_bucket")
}

fn validate_flavor(value: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > 64 {
        return Err("flavor must contain 1..64 characters".to_owned());
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || ".-_".contains(ch))
    {
        return Err("flavor contains unsupported characters".to_owned());
    }
    Ok(())
}

fn validate_job_name(value: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > 128 {
        return Err("job_name must contain 1..128 characters".to_owned());
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "-_".contains(ch))
    {
        return Err("job_name contains unsupported characters".to_owned());
    }
    Ok(())
}

fn image_digest(value: &str) -> Result<String, String> {
    if value.is_empty() || value.len() > 512 || value.chars().any(char::is_whitespace) {
        return Err("HF Jobs image reference is empty, too long, or contains whitespace".to_owned());
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "./:@_-".contains(ch))
    {
        return Err("HF Jobs image reference contains unsupported characters".to_owned());
    }
    let Some((name, digest)) = value.rsplit_once("@sha256:") else {
        return Err("HF Jobs image must be immutable and digest-pinned with @sha256:<64 hex>".to_owned());
    };
    if name.is_empty() || digest.len() != 64 || !digest.chars().all(|ch| ch.is_ascii_hexdigit()) {
        return Err("HF Jobs image has an invalid sha256 digest".to_owned());
    }
    Ok(format!("sha256:{}", digest.to_ascii_lowercase()))
}

fn write_plan(path: &Path, plan: &HfJobPlan) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("{}: {error}", parent.display()))?;
    }
    let mut text = serde_json::to_string_pretty(plan).map_err(|error| error.to_string())?;
    text.push('\n');
    fs::write(path, text).map_err(|error| format!("{}: {error}", path.display()))
}

fn read_plan(path: &Path) -> Result<HfJobPlan, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    serde_json::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))
}

fn plan_sha256(plan: &HfJobPlan) -> Result<String, String> {
    let bytes = serde_json::to_vec(plan).map_err(|error| error.to_string())?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn digest_image() -> String {
        format!("ghcr.io/owner/package@sha256:{}", "a".repeat(64))
    }

    #[test]
    fn builds_bucket_cpu_plan() {
        let plan = build_plan(PlanInput {
            built_image: digest_image(),
            image_override: String::new(),
            candidate_id: "candidate-000123".to_owned(),
            suite: "probe".to_owned(),
            environment: "linux-cpu".to_owned(),
            provider: "CPUExecutionProvider".to_owned(),
            hf_bucket: "owner/project-bucket".to_owned(),
            dataset_source: "bucket".to_owned(),
            dataset_id: String::new(),
            flavor: "cpu-basic".to_owned(),
            run_id: 9001,
            run_attempt: 2,
        })
        .unwrap();
        validate_plan(&plan).unwrap();
        assert_eq!(plan.mounts.len(), 1);
        assert_eq!(plan.dataset_dir, "/jpapt-output/datasets");
        assert_eq!(plan.image_digest, format!("sha256:{}", "a".repeat(64)));
        assert_eq!(
            plan.result_uri,
            "hf://buckets/owner/project-bucket/runs/hf-jobs/candidate-000123/probe-9001-2/result.json"
        );
        assert_eq!(plan.hf_args[0..2], ["jobs", "run"]);
        assert_eq!(
            plan.hf_args.last().unwrap(),
            &format!("{}/result.json", plan.output_dir)
        );
    }

    #[test]
    fn builds_custom_cuda_plan_with_dataset_mount() {
        let plan = build_plan(PlanInput {
            built_image: digest_image(),
            image_override: format!("registry.example.com/model@sha256:{}", "b".repeat(64)),
            candidate_id: "candidate-000999".to_owned(),
            suite: "smoke".to_owned(),
            environment: "linux-cuda".to_owned(),
            provider: "CUDAExecutionProvider".to_owned(),
            hf_bucket: "owner/project-bucket".to_owned(),
            dataset_source: "custom".to_owned(),
            dataset_id: "japanese-asr/jsut".to_owned(),
            flavor: "a10g-small".to_owned(),
            run_id: 9002,
            run_attempt: 1,
        })
        .unwrap();
        validate_plan(&plan).unwrap();
        assert_eq!(plan.mounts.len(), 2);
        assert_eq!(plan.dataset_dir, "/data");
        assert_eq!(plan.image_digest, format!("sha256:{}", "b".repeat(64)));
        assert!(
            plan.hf_args
                .iter()
                .any(|arg| arg == "hf://datasets/japanese-asr/jsut:/data:ro")
        );
    }

    #[test]
    fn rejects_mutable_image_tag() {
        let error = build_plan(PlanInput {
            built_image: "ghcr.io/owner/package:latest".to_owned(),
            image_override: String::new(),
            candidate_id: "candidate-000001".to_owned(),
            suite: "probe".to_owned(),
            environment: "linux-cpu".to_owned(),
            provider: "CPUExecutionProvider".to_owned(),
            hf_bucket: "owner/project-bucket".to_owned(),
            dataset_source: "bucket".to_owned(),
            dataset_id: String::new(),
            flavor: "cpu-basic".to_owned(),
            run_id: 1,
            run_attempt: 1,
        })
        .unwrap_err();
        assert!(error.contains("digest-pinned"));
    }

    #[test]
    fn rejects_environment_provider_mismatch() {
        let error = build_plan(PlanInput {
            built_image: digest_image(),
            image_override: String::new(),
            candidate_id: "candidate-000001".to_owned(),
            suite: "probe".to_owned(),
            environment: "linux-cuda".to_owned(),
            provider: "CPUExecutionProvider".to_owned(),
            hf_bucket: "owner/project-bucket".to_owned(),
            dataset_source: "bucket".to_owned(),
            dataset_id: String::new(),
            flavor: "cpu-basic".to_owned(),
            run_id: 1,
            run_attempt: 1,
        })
        .unwrap_err();
        assert!(error.contains("CUDAExecutionProvider"));
    }

    #[test]
    fn rejects_tampered_argv() {
        let mut plan = build_plan(PlanInput {
            built_image: digest_image(),
            image_override: String::new(),
            candidate_id: "candidate-000001".to_owned(),
            suite: "probe".to_owned(),
            environment: "linux-cpu".to_owned(),
            provider: "CPUExecutionProvider".to_owned(),
            hf_bucket: "owner/project-bucket".to_owned(),
            dataset_source: "bucket".to_owned(),
            dataset_id: String::new(),
            flavor: "cpu-basic".to_owned(),
            run_id: 1,
            run_attempt: 1,
        })
        .unwrap();
        plan.hf_args.push("--unexpected".to_owned());
        let error = validate_plan(&plan).unwrap_err();
        assert!(error.contains("hf_args"));
    }

    #[test]
    fn rejects_tampered_image_digest() {
        let mut plan = build_plan(PlanInput {
            built_image: digest_image(),
            image_override: String::new(),
            candidate_id: "candidate-000001".to_owned(),
            suite: "probe".to_owned(),
            environment: "linux-cpu".to_owned(),
            provider: "CPUExecutionProvider".to_owned(),
            hf_bucket: "owner/project-bucket".to_owned(),
            dataset_source: "bucket".to_owned(),
            dataset_id: String::new(),
            flavor: "cpu-basic".to_owned(),
            run_id: 1,
            run_attempt: 1,
        })
        .unwrap();
        plan.image_digest = format!("sha256:{}", "f".repeat(64));
        let error = validate_plan(&plan).unwrap_err();
        assert!(error.contains("image_digest"));
    }
}
