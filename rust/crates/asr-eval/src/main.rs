use std::str::FromStr;

use asr_eval::evaluator::{evaluate, EvaluateOptions};
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
    }
    Ok(())
}
