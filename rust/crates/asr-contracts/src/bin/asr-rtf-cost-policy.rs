use std::{env, fs};

use asr_contracts::rtf_cost::{RtfCostPolicy, RtfCostRequest, validate_rtf_cost_plan};

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-rtf-cost-policy: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let mut provider = None;
    let mut gpu = None;
    let mut batch_size = None;
    let mut repeat = None;
    let mut sample_count = None;
    let mut target_total_sec = None;
    let mut max_duration_sec = None;
    let mut mode = "guarded".to_owned();
    let mut allow_expensive_matrix = false;
    let mut policy_path = None;
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        let mut value = || {
            args.next()
                .ok_or_else(|| format!("missing value for {arg}"))
        };
        match arg.as_str() {
            "--provider" => provider = Some(value()?),
            "--gpu" => gpu = Some(value()?),
            "--batch-size" => batch_size = Some(parse(value()?, "batch-size")?),
            "--repeat" => repeat = Some(parse(value()?, "repeat")?),
            "--sample-count" => sample_count = Some(parse(value()?, "sample-count")?),
            "--target-total-sec" => target_total_sec = Some(parse(value()?, "target-total-sec")?),
            "--max-duration-sec" => max_duration_sec = Some(parse(value()?, "max-duration-sec")?),
            "--mode" => mode = value()?,
            "--policy" => policy_path = Some(value()?),
            "--allow-expensive-matrix" => allow_expensive_matrix = true,
            _ => return Err(format!("unknown option {arg}")),
        }
    }
    let policy_path = policy_path.ok_or("--policy is required")?;
    let policy: RtfCostPolicy = serde_json::from_str(
        &fs::read_to_string(&policy_path)
            .map_err(|error| format!("failed to read --policy {policy_path}: {error}"))?,
    )
    .map_err(|error| format!("invalid --policy JSON {policy_path}: {error}"))?;
    let plan = validate_rtf_cost_plan(
        &RtfCostRequest {
            provider: provider.ok_or("--provider is required")?,
            gpu: gpu.ok_or("--gpu is required")?,
            batch_size: batch_size.ok_or("--batch-size is required")?,
            repeat: repeat.ok_or("--repeat is required")?,
            sample_count: sample_count.ok_or("--sample-count is required")?,
            target_total_sec: target_total_sec.ok_or("--target-total-sec is required")?,
            max_duration_sec: max_duration_sec.ok_or("--max-duration-sec is required")?,
            mode,
            allow_expensive_matrix,
        },
        &policy,
    )
    .map_err(|error| error.to_string())?;
    println!(
        "{}",
        serde_json::to_string(&plan).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn parse(value: String, name: &str) -> Result<u32, String> {
    value
        .parse()
        .map_err(|error| format!("invalid --{name}: {error}"))
}
