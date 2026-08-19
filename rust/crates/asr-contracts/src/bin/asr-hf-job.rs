use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const SCHEMA_VERSION: u32 = 2;
const SMOKE_SUITE: &str = "smoke";
const SMOKE_TIMEOUT: &str = "30m";
const SMOKE_RESULT_PATH: &str = "results/candidate-package/result.json";

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
    timeout: String,
    run_id: u64,
    run_attempt: u64,
    labels: Vec<String>,
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
        "validate-result" => validate_result_command(flags),
        "preflight" => preflight_command(flags),
        "run" => run_command(flags),
        _ => Err(usage()),
    }
}

fn usage() -> String {
    "usage: asr-hf-job plan --built-image REF [--image-override REF] --candidate-id candidate-NNNNNN --suite smoke --environment linux-cpu|linux-cuda --provider PROVIDER --hf-bucket namespace/name --dataset-source bucket|repository|custom [--dataset-id namespace/name] --flavor FLAVOR --run-id N --run-attempt N --output-json PATH [--github-output PATH] | validate --plan PATH | validate-result --plan PATH --result PATH | preflight --plan PATH | run --plan PATH".to_owned()
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
        run_attempt: positive_u64(required(&mut flags, "--run-attempt")?, "--run-attempt")?,
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
            "job_name={}\nimage={}\nimage_digest={}\nresult_uri={}\noutput_dir={}\ndataset_dir={}\ntimeout={}\nplan_sha256={}\n",
            plan.job_name,
            plan.image,
            plan.image_digest,
            plan.result_uri,
            plan.output_dir,
            plan.dataset_dir,
            plan.timeout,
            digest
        );
        fs::write(&github_output, text).map_err(|error| format!("{github_output}: {error}"))?;
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

fn validate_result_command(mut flags: BTreeMap<String, String>) -> Result<(), String> {
    let plan_path = PathBuf::from(required(&mut flags, "--plan")?);
    let result_path = PathBuf::from(required(&mut flags, "--result")?);
    no_flags(flags)?;
    let plan = read_plan(&plan_path)?;
    validate_plan(&plan)?;
    let result = read_json(&result_path)?;
    let summary = validate_smoke_result(&plan, &result)?;
    println!(
        "{}",
        serde_json::to_string(&summary).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn preflight_command(mut flags: BTreeMap<String, String>) -> Result<(), String> {
    let plan_path = PathBuf::from(required(&mut flags, "--plan")?);
    no_flags(flags)?;
    let plan = read_plan(&plan_path)?;
    validate_plan(&plan)?;
    required_hf_token()?;
    preflight_hardware(&plan)?;
    println!("{}", plan.flavor);
    Ok(())
}

fn run_command(mut flags: BTreeMap<String, String>) -> Result<(), String> {
    let plan_path = PathBuf::from(required(&mut flags, "--plan")?);
    no_flags(flags)?;
    let plan = read_plan(&plan_path)?;
    validate_plan(&plan)?;
    required_hf_token()?;
    preflight_hardware(&plan)?;

    eprintln!(
        "[asr-hf-job] invoking hf with validated smoke plan sha256={} argv={}",
        plan_sha256(&plan)?,
        serde_json::to_string(&plan.hf_args).map_err(|error| error.to_string())?
    );
    let status = Command::new("hf")
        .args(&plan.hf_args)
        .status()
        .map_err(|error| format!("failed to execute hf CLI: {error}"))?;

    let result_path = PathBuf::from(SMOKE_RESULT_PATH);
    if !status.success() {
        match fetch_smoke_result(&plan, &result_path) {
            Ok(()) => eprintln!(
                "[asr-hf-job] preserved remote failure evidence at {}",
                result_path.display()
            ),
            Err(error) => eprintln!(
                "[asr-hf-job] remote job failed and result evidence could not be fetched: {error}"
            ),
        }
        return Err(format!("hf jobs run failed with status {status}"));
    }

    fetch_smoke_result(&plan, &result_path)?;
    let result = read_json(&result_path)?;
    let summary = validate_smoke_result(&plan, &result)?;
    eprintln!(
        "[asr-hf-job] validated remote smoke result {}",
        serde_json::to_string(&summary).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn required_hf_token() -> Result<(), String> {
    match env::var("HF_TOKEN") {
        Ok(value) if !value.trim().is_empty() => Ok(()),
        _ => Err("HF_TOKEN is required before invoking Hugging Face Jobs".to_owned()),
    }
}

fn preflight_hardware(plan: &HfJobPlan) -> Result<(), String> {
    let output = Command::new("hf")
        .args(["jobs", "hardware"])
        .output()
        .map_err(|error| format!("failed to execute hf jobs hardware: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "hf jobs hardware failed with status {}: {}",
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    let stdout = String::from_utf8(output.stdout)
        .map_err(|error| format!("hf jobs hardware returned non-UTF-8 output: {error}"))?;
    if !hardware_output_has_flavor(&stdout, &plan.flavor) {
        return Err(format!(
            "requested HF Jobs flavor {:?} is not present in hf jobs hardware output",
            plan.flavor
        ));
    }
    eprintln!(
        "[asr-hf-job] hardware preflight accepted flavor={}",
        plan.flavor
    );
    Ok(())
}

fn fetch_smoke_result(plan: &HfJobPlan, result_path: &Path) -> Result<(), String> {
    if let Some(parent) = result_path.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("{}: {error}", parent.display()))?;
    }
    let destination = result_path
        .to_str()
        .ok_or_else(|| "smoke result destination is not valid UTF-8".to_owned())?;
    let status = Command::new("hf")
        .args(["buckets", "cp", &plan.result_uri, destination])
        .status()
        .map_err(|error| format!("failed to fetch HF Jobs smoke result: {error}"))?;
    if !status.success() {
        return Err(format!(
            "failed to fetch HF Jobs smoke result {} with status {status}",
            plan.result_uri
        ));
    }
    Ok(())
}

fn hardware_output_has_flavor(output: &str, flavor: &str) -> bool {
    output
        .lines()
        .flat_map(|line| line.split_whitespace())
        .map(|token| {
            token.trim_matches(|ch: char| !ch.is_ascii_alphanumeric() && !".-_".contains(ch))
        })
        .any(|token| token == flavor)
}

fn build_plan(input: PlanInput) -> Result<HfJobPlan, String> {
    validate_candidate_id(&input.candidate_id)?;
    if input.suite != SMOKE_SUITE {
        return Err("HF Jobs execution is smoke-only; suite must be smoke".to_owned());
    }
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

    let suffix = format!("{}-{}-{}", SMOKE_SUITE, input.run_id, input.run_attempt);
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
        input.candidate_id, SMOKE_SUITE, input.run_id, input.run_attempt
    );
    validate_job_name(&job_name)?;

    let labels = vec![
        "jpapt-purpose=smoke-validation".to_owned(),
        format!("jpapt-candidate={}", input.candidate_id),
        format!("jpapt-run={}-{}", input.run_id, input.run_attempt),
    ];

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
        suite: SMOKE_SUITE.to_owned(),
        environment: input.environment,
        provider: input.provider,
        hf_bucket: input.hf_bucket,
        dataset_source: input.dataset_source,
        dataset_id: input.dataset_id,
        dataset_dir,
        output_dir,
        result_uri,
        timeout: SMOKE_TIMEOUT.to_owned(),
        run_id: input.run_id,
        run_attempt: input.run_attempt,
        labels,
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
        "--timeout".to_owned(),
        plan.timeout.clone(),
    ];
    for label in &plan.labels {
        args.push("--label".to_owned());
        args.push(label.clone());
    }
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
    if plan.suite != SMOKE_SUITE {
        return Err("HF Jobs execution is smoke-only; persisted suite must be smoke".to_owned());
    }
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
    if plan.timeout != SMOKE_TIMEOUT {
        return Err(format!(
            "HF Jobs smoke timeout must be canonical {SMOKE_TIMEOUT}"
        ));
    }
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
        plan.candidate_id, SMOKE_SUITE, plan.run_id, plan.run_attempt
    );
    if plan.output_dir != expected_output_dir {
        return Err("output_dir does not match canonical HF Jobs smoke layout".to_owned());
    }
    let expected_result_uri = format!(
        "hf://buckets/{}/runs/hf-jobs/{}/{}-{}-{}/result.json",
        plan.hf_bucket, plan.candidate_id, SMOKE_SUITE, plan.run_id, plan.run_attempt
    );
    if plan.result_uri != expected_result_uri {
        return Err("result_uri does not match canonical HF Jobs smoke layout".to_owned());
    }

    let expected_labels = vec![
        "jpapt-purpose=smoke-validation".to_owned(),
        format!("jpapt-candidate={}", plan.candidate_id),
        format!("jpapt-run={}-{}", plan.run_id, plan.run_attempt),
    ];
    if plan.labels != expected_labels {
        return Err("labels do not match canonical HF Jobs smoke labels".to_owned());
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
        return Err("hf_args does not match canonical HF Jobs smoke command".to_owned());
    }
    Ok(())
}

fn validate_smoke_result(plan: &HfJobPlan, result: &Value) -> Result<Value, String> {
    let result = result
        .as_object()
        .ok_or_else(|| "HF Jobs smoke result must be a JSON object".to_owned())?;
    if result.get("schema_version").and_then(Value::as_u64) != Some(2) {
        return Err("HF Jobs smoke result schema_version must be 2".to_owned());
    }
    if result.get("suite").and_then(Value::as_str) != Some(SMOKE_SUITE) {
        return Err("HF Jobs result suite must be smoke".to_owned());
    }
    if result.get("requested_provider").and_then(Value::as_str) != Some(plan.provider.as_str()) {
        return Err("result.requested_provider does not match the HF Jobs plan".to_owned());
    }
    if result
        .get("requested_provider_available")
        .and_then(Value::as_bool)
        != Some(true)
    {
        return Err("requested provider was unavailable in HF Jobs smoke result".to_owned());
    }
    if result.get("provider").and_then(Value::as_str) != Some(plan.provider.as_str()) {
        return Err("result.provider does not match the strict requested provider".to_owned());
    }
    if result.get("provider_fallback").and_then(Value::as_bool) != Some(false) {
        return Err("provider fallback is not permitted in HF Jobs smoke evidence".to_owned());
    }
    if plan.provider != "CPUExecutionProvider"
        && result
            .get("cpu_ep_fallback_disabled")
            .and_then(Value::as_bool)
            != Some(true)
    {
        return Err("non-CPU HF Jobs smoke evidence must disable CPU EP fallback".to_owned());
    }
    if result.get("passed").and_then(Value::as_bool) != Some(true) {
        return Err(format!(
            "HF Jobs smoke result did not pass: failure={}",
            result
                .get("failure")
                .and_then(Value::as_str)
                .unwrap_or("unspecified")
        ));
    }
    if result.get("failure").is_some_and(|value| !value.is_null()) {
        return Err("passed HF Jobs smoke result must not contain failure evidence".to_owned());
    }

    let models = result
        .get("models")
        .and_then(Value::as_array)
        .filter(|models| !models.is_empty())
        .ok_or_else(|| "HF Jobs smoke result must contain at least one model".to_owned())?;
    for (index, model) in models.iter().enumerate() {
        let model = model
            .as_object()
            .ok_or_else(|| format!("result.models[{index}] must be an object"))?;
        if model.get("passed").and_then(Value::as_bool) != Some(true) {
            return Err(format!("result.models[{index}] did not pass"));
        }
        let active = model
            .get("active_providers")
            .and_then(Value::as_array)
            .ok_or_else(|| format!("result.models[{index}].active_providers must be an array"))?;
        if !active
            .iter()
            .any(|value| value.as_str() == Some(plan.provider.as_str()))
        {
            return Err(format!(
                "result.models[{index}] does not register requested provider {}",
                plan.provider
            ));
        }
    }

    let cases = result
        .get("cases")
        .and_then(Value::as_array)
        .filter(|cases| !cases.is_empty())
        .ok_or_else(|| "HF Jobs smoke result must contain smoke case evidence".to_owned())?;
    if cases.len() != 1 {
        return Err(format!(
            "HF Jobs smoke result must contain exactly one case evidence entry; got {}",
            cases.len()
        ));
    }
    for (index, case) in cases.iter().enumerate() {
        let case = case
            .as_object()
            .ok_or_else(|| format!("result.cases[{index}] must be an object"))?;
        if case.get("passed").and_then(Value::as_bool) != Some(true) {
            return Err(format!("result.cases[{index}] did not pass"));
        }
    }

    Ok(serde_json::json!({
        "schema_version": 1,
        "suite": SMOKE_SUITE,
        "candidate_id": plan.candidate_id,
        "provider": plan.provider,
        "result_uri": plan.result_uri,
        "model_count": models.len(),
        "case_count": cases.len(),
        "passed": true
    }))
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
        return Err(
            "HF Jobs image reference is empty, too long, or contains whitespace".to_owned(),
        );
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "./:@_-".contains(ch))
    {
        return Err("HF Jobs image reference contains unsupported characters".to_owned());
    }
    let Some((name, digest)) = value.rsplit_once("@sha256:") else {
        return Err(
            "HF Jobs image must be immutable and digest-pinned with @sha256:<64 hex>".to_owned(),
        );
    };
    if name.is_empty()
        || digest.len() != 64
        || !digest
            .chars()
            .all(|ch| ch.is_ascii_hexdigit() && !ch.is_ascii_uppercase())
    {
        return Err("HF Jobs image has an invalid lowercase sha256 digest".to_owned());
    }
    Ok(format!("sha256:{digest}"))
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

fn read_json(path: &Path) -> Result<Value, String> {
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

    fn smoke_input() -> PlanInput {
        PlanInput {
            built_image: digest_image(),
            image_override: String::new(),
            candidate_id: "candidate-000123".to_owned(),
            suite: SMOKE_SUITE.to_owned(),
            environment: "linux-cpu".to_owned(),
            provider: "CPUExecutionProvider".to_owned(),
            hf_bucket: "owner/project-bucket".to_owned(),
            dataset_source: "bucket".to_owned(),
            dataset_id: String::new(),
            flavor: "cpu-basic".to_owned(),
            run_id: 9001,
            run_attempt: 2,
        }
    }

    fn smoke_result(provider: &str) -> Value {
        serde_json::json!({
            "schema_version": 2,
            "suite": "smoke",
            "requested_provider": provider,
            "requested_provider_available": true,
            "provider": provider,
            "provider_fallback": false,
            "cpu_ep_fallback_disabled": provider != "CPUExecutionProvider",
            "available_providers": [provider],
            "models": [{
                "path": "encoder.onnx",
                "passed": true,
                "active_providers": [provider]
            }],
            "cases": [{"case": null, "passed": true, "note": "structural smoke"}],
            "passed": true
        })
    }

    #[test]
    fn builds_bucket_cpu_smoke_plan() {
        let plan = build_plan(smoke_input()).unwrap();
        validate_plan(&plan).unwrap();
        assert_eq!(plan.schema_version, 2);
        assert_eq!(plan.suite, SMOKE_SUITE);
        assert_eq!(plan.timeout, SMOKE_TIMEOUT);
        assert_eq!(plan.mounts.len(), 1);
        assert_eq!(plan.dataset_dir, "/jpapt-output/datasets");
        assert_eq!(plan.image_digest, format!("sha256:{}", "a".repeat(64)));
        assert_eq!(
            plan.result_uri,
            "hf://buckets/owner/project-bucket/runs/hf-jobs/candidate-000123/smoke-9001-2/result.json"
        );
        assert!(
            plan.hf_args
                .windows(2)
                .any(|pair| pair == ["--timeout", "30m"])
        );
        assert!(
            plan.hf_args
                .windows(2)
                .any(|pair| pair == ["--label", "jpapt-purpose=smoke-validation"])
        );
    }

    #[test]
    fn builds_custom_cuda_smoke_plan_with_dataset_mount() {
        let plan = build_plan(PlanInput {
            built_image: digest_image(),
            image_override: format!("registry.example.com/model@sha256:{}", "b".repeat(64)),
            candidate_id: "candidate-000999".to_owned(),
            suite: SMOKE_SUITE.to_owned(),
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
    fn rejects_probe_and_parity_plans() {
        for suite in ["probe", "parity"] {
            let mut input = smoke_input();
            input.suite = suite.to_owned();
            let error = build_plan(input).unwrap_err();
            assert!(error.contains("smoke-only"));
        }
    }

    #[test]
    fn rejects_mutable_image_tag() {
        let mut input = smoke_input();
        input.built_image = "ghcr.io/owner/package:latest".to_owned();
        let error = build_plan(input).unwrap_err();
        assert!(error.contains("digest-pinned"));
    }

    #[test]
    fn rejects_uppercase_built_image_digest() {
        let mut input = smoke_input();
        input.built_image = format!("ghcr.io/owner/package@sha256:{}", "A".repeat(64));
        let error = build_plan(input).unwrap_err();
        assert!(error.contains("lowercase sha256"));
    }

    #[test]
    fn rejects_uppercase_override_image_digest() {
        let mut input = smoke_input();
        input.image_override = format!("ghcr.io/owner/package@sha256:{}", "A".repeat(64));
        let error = build_plan(input).unwrap_err();
        assert!(error.contains("lowercase sha256"));
    }

    #[test]
    fn rejects_environment_provider_mismatch() {
        let mut input = smoke_input();
        input.environment = "linux-cuda".to_owned();
        let error = build_plan(input).unwrap_err();
        assert!(error.contains("CUDAExecutionProvider"));
    }

    #[test]
    fn rejects_tampered_argv() {
        let mut plan = build_plan(smoke_input()).unwrap();
        plan.hf_args.push("--unexpected".to_owned());
        let error = validate_plan(&plan).unwrap_err();
        assert!(error.contains("hf_args"));
    }

    #[test]
    fn rejects_tampered_image_digest() {
        let mut plan = build_plan(smoke_input()).unwrap();
        plan.image_digest = format!("sha256:{}", "f".repeat(64));
        let error = validate_plan(&plan).unwrap_err();
        assert!(error.contains("image_digest"));
    }

    #[test]
    fn rejects_tampered_timeout_and_suite() {
        let mut plan = build_plan(smoke_input()).unwrap();
        plan.timeout = "2h".to_owned();
        assert!(validate_plan(&plan).unwrap_err().contains("timeout"));

        let mut plan = build_plan(smoke_input()).unwrap();
        plan.suite = "parity".to_owned();
        assert!(validate_plan(&plan).unwrap_err().contains("smoke-only"));
    }

    #[test]
    fn matches_flavor_as_exact_hardware_token() {
        let output = "FLAVOR       CPU   GPU\ncpu-basic    2     -\na10g-small   4     A10G\n";
        assert!(hardware_output_has_flavor(output, "cpu-basic"));
        assert!(hardware_output_has_flavor(output, "a10g-small"));
        assert!(!hardware_output_has_flavor(output, "a10g"));
        assert!(!hardware_output_has_flavor(output, "h200"));
    }

    #[test]
    fn validates_strict_smoke_result() {
        let plan = build_plan(smoke_input()).unwrap();
        let summary = validate_smoke_result(&plan, &smoke_result("CPUExecutionProvider")).unwrap();
        assert_eq!(summary["passed"], true);
        assert_eq!(summary["model_count"], 1);
        assert_eq!(summary["case_count"], 1);
    }

    #[test]
    fn validates_strict_cuda_smoke_result() {
        let plan = build_plan(PlanInput {
            environment: "linux-cuda".to_owned(),
            provider: "CUDAExecutionProvider".to_owned(),
            flavor: "a10g-small".to_owned(),
            ..smoke_input()
        })
        .unwrap();
        validate_smoke_result(&plan, &smoke_result("CUDAExecutionProvider")).unwrap();
    }

    #[test]
    fn rejects_smoke_result_fallback_or_provider_drift() {
        let plan = build_plan(smoke_input()).unwrap();
        let mut result = smoke_result("CPUExecutionProvider");
        result["provider_fallback"] = Value::Bool(true);
        assert!(
            validate_smoke_result(&plan, &result)
                .unwrap_err()
                .contains("fallback")
        );

        let mut result = smoke_result("CPUExecutionProvider");
        result["provider"] = Value::String("CUDAExecutionProvider".to_owned());
        assert!(
            validate_smoke_result(&plan, &result)
                .unwrap_err()
                .contains("provider")
        );
    }

    #[test]
    fn rejects_failed_smoke_model_or_case() {
        let plan = build_plan(smoke_input()).unwrap();
        let mut result = smoke_result("CPUExecutionProvider");
        result["models"][0]["passed"] = Value::Bool(false);
        assert!(
            validate_smoke_result(&plan, &result)
                .unwrap_err()
                .contains("models[0]")
        );

        let mut result = smoke_result("CPUExecutionProvider");
        result["cases"][0]["passed"] = Value::Bool(false);
        assert!(
            validate_smoke_result(&plan, &result)
                .unwrap_err()
                .contains("cases[0]")
        );
    }

    #[test]
    fn rejects_multiple_smoke_cases() {
        let plan = build_plan(smoke_input()).unwrap();
        let mut result = smoke_result("CPUExecutionProvider");
        result["cases"] = serde_json::json!([
            {"case": "a", "passed": true},
            {"case": "b", "passed": true}
        ]);
        assert!(
            validate_smoke_result(&plan, &result)
                .unwrap_err()
                .contains("exactly one")
        );
    }
}
