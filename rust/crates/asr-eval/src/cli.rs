use std::path::PathBuf;
use clap::{Parser,Subcommand,Args};

#[derive(Debug,Parser)]
#[command(name="asr-eval",version,about="Rust-first ONNX ASR evaluator")]
pub struct Cli { #[command(subcommand)] pub command:Command }

#[derive(Debug,Subcommand)] pub enum Command { Evaluate(EvaluateArgs) }

#[derive(Debug,Args)] pub struct EvaluateArgs {
 #[arg(long)] pub provider:String,
 #[arg(long)] pub model:PathBuf,
 #[arg(long)] pub candidate_dir:PathBuf,
 #[arg(long)] pub candidate_id:Option<String>,
 #[arg(long)] pub vocabulary:PathBuf,
 #[arg(long)] pub resolved_manifest:PathBuf,
 #[arg(long,default_value="smoke")] pub evaluation:String,
 #[arg(long,default_value="parakeet-tdt_ctc-0.6b-ja")] pub model_id:String,
 #[arg(long,default_value=".ci/hf/config/revisions")] pub revisions:PathBuf,
 #[arg(long)] pub output:PathBuf,
}
