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
    BucketInit(BucketInitArgs),
    NemoOnnxValidate(NemoOnnxValidateArgs),
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

#[derive(Debug, Args)]
pub struct BucketInitArgs {
    #[arg(long)]
    pub bucket_id: String,
    #[arg(long)]
    pub model_repo: String,
    #[arg(long)]
    pub model_revision: String,
    #[arg(long)]
    pub expected_task: String,
    #[arg(long)]
    pub expected_library: String,
    #[arg(long)]
    pub expected_language: String,
    #[arg(long)]
    pub expected_license: String,
    #[arg(long)]
    pub expected_architecture: String,
    #[arg(long)]
    pub profile_set: String,
    #[arg(long)]
    pub confirmation: String,
    #[arg(long, default_value_t = false)]
    pub apply: bool,
}

#[derive(Debug, Args)]
pub struct NemoOnnxValidateArgs {
    #[arg(long)]
    pub report: PathBuf,
    #[arg(long)]
    pub bundle_root: PathBuf,
    #[arg(long, default_value = "ctc")]
    pub require: String,
}
