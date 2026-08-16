use std::str::FromStr;

use asr_eval::bucket_init::{BucketInitOptions, initialize_bucket};
use asr_eval::evaluator::{EvaluateOptions, evaluate};
use asr_eval::nemo_onnx::{RequiredScope, validate_report};
use asr_eval::{Cli, Command};
use asr_runtime::ProviderKind;
use clap::Parser;

fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();
    let cli = Cli::parse();
    match cli.command {
        Command::Evaluate(args) => {
            let provider = ProviderKind::from_str(&args.provider)?;
            let result = evaluate(EvaluateOptions {
                provider,
                candidate_contract: args.candidate_contract,
                run_context: args.run_context,
                resolved_manifest: args.resolved_manifest,
                output: args.output,
            })?;
            println!("run_id: {}", result["run_id"]);
            println!("acceptance.passed: {}", result["acceptance"]["passed"]);
            if result["acceptance"]["passed"] == false {
                std::process::exit(1);
            }
        }
        Command::BucketInit(args) => {
            let manifest = initialize_bucket(BucketInitOptions {
                bucket_id: args.bucket_id,
                model_repo: args.model_repo,
                model_revision: args.model_revision,
                expected_task: args.expected_task,
                expected_library: args.expected_library,
                expected_language: args.expected_language,
                expected_license: args.expected_license,
                expected_architecture: args.expected_architecture,
                profile_set: args.profile_set,
                confirmation: args.confirmation,
                apply: args.apply,
            })?;
            println!("{}", serde_json::to_string_pretty(&manifest)?);
        }
        Command::NemoOnnxValidate(args) => {
            let scope = RequiredScope::parse(&args.require)?;
            let report = validate_report(&args.report, &args.bundle_root, scope)?;
            println!("validated NeMo ONNX report: schema_version={} profile_id={}", report.schema_version(), report.profile_id());
        }
    }
    Ok(())
}
