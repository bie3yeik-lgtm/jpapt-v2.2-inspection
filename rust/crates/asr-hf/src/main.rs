use std::path::PathBuf;

use asr_hf::{ResolveTargetOptions, TargetSelector, append_github_file, resolve_target};
use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(name = "asr-hf")]
#[command(about = "Deterministic Hugging Face target and layout policy for jpapt")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    ResolveTarget {
        #[arg(long, conflicts_with = "bucket", required_unless_present = "bucket")]
        target: Option<String>,
        #[arg(long, conflicts_with = "target", required_unless_present = "target")]
        bucket: Option<String>,
        #[arg(long)]
        runtime_variant: Option<String>,
        #[arg(long, default_value = ".")]
        repository_root: PathBuf,
        #[arg(long)]
        targets_json: Option<String>,
        #[arg(long)]
        github_env: Option<PathBuf>,
        #[arg(long)]
        github_output: Option<PathBuf>,
        #[arg(long)]
        shell: bool,
    },
}

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-hf: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    match Cli::parse().command {
        Command::ResolveTarget {
            target,
            bucket,
            runtime_variant,
            repository_root,
            targets_json,
            github_env,
            github_output,
            shell,
        } => {
            let selector = match (target, bucket) {
                (Some(value), None) => TargetSelector::Id(value),
                (None, Some(value)) => TargetSelector::Bucket(value),
                _ => unreachable!("clap enforces exactly one selector"),
            };
            let resolved = resolve_target(&ResolveTargetOptions {
                repository_root,
                selector,
                runtime_variant,
                targets_json,
            })?;
            if let Some(path) = github_env {
                append_github_file(&path, &resolved.environment_values())?;
            }
            if let Some(path) = github_output {
                append_github_file(&path, &resolved.output_values())?;
            }
            if shell {
                for (key, value) in resolved.environment_values() {
                    println!("export {key}={}", shell_quote(value));
                }
            } else {
                for (key, value) in resolved.environment_values() {
                    println!("{key}={value}");
                }
            }
        }
    }
    Ok(())
}

fn shell_quote(value: &str) -> String {
    if value
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || b"_@%+=:,./-".contains(&byte))
    {
        value.to_owned()
    } else {
        format!("'{}'", value.replace('\'', "'\\''"))
    }
}
