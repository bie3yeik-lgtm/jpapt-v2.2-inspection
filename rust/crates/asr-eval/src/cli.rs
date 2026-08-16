use std::path::PathBuf;

use clap::{Args, Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(name = "asr-eval", version, about = "Rust ONNX ASR execution engine")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Subcommand)]
pub enum Command {
    Evaluate(EvaluateArgs),
}

#[derive(Debug, Args)]
pub struct EvaluateArgs {
    #[arg(long)]
    pub provider: String,
    #[arg(long)]
    pub candidate_contract: PathBuf,
    #[arg(long)]
    pub run_context: PathBuf,
    #[arg(long)]
    pub resolved_manifest: PathBuf,
    #[arg(long)]
    pub output: PathBuf,
}
