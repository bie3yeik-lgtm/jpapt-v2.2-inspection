use std::str::FromStr;
use clap::Parser;
use asr_eval::{Cli,Command};
use asr_eval::evaluator::{EvaluateOptions,evaluate};
use asr_runtime::ProviderKind;

fn main() -> anyhow::Result<()> {
 tracing_subscriber::fmt().with_env_filter(tracing_subscriber::EnvFilter::from_default_env()).init();
 let cli=Cli::parse();
 match cli.command {
  Command::Evaluate(args)=>{
   let provider=ProviderKind::from_str(&args.provider)?;
   let result=evaluate(EvaluateOptions{
    provider,
    model:args.model,
    candidate_dir:args.candidate_dir,
    candidate_id:args.candidate_id,
    experiment_id:args.experiment_id,
    vocabulary:args.vocabulary,
    resolved_manifest:args.resolved_manifest,
    evaluation:args.evaluation,
    model_id:args.model_id,
    revisions:args.revisions,
    output:args.output
   })?;
   println!("run_id: {}",result["run_id"]);
   println!("acceptance.passed: {}",result["acceptance"]["passed"]);
   if result["acceptance"]["passed"]==false { std::process::exit(1); }
  }
 }
 Ok(())
}
