use std::fs;
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
    ValidateTargets {
        #[arg(long, default_value = ".")]
        repository_root: PathBuf,
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
        Command::ValidateTargets { repository_root } => {
            let root = repository_root.canonicalize()?;
            let target_root = root.join("config/hf-targets");
            if !target_root.is_dir() {
                return Err(format!("{} is missing", target_root.display()).into());
            }
            let mut paths = fs::read_dir(&target_root)?
                .filter_map(|entry| entry.ok().map(|entry| entry.path()))
                .filter(|path| path.extension().and_then(|value| value.to_str()) == Some("toml"))
                .collect::<Vec<_>>();
            paths.sort();
            if paths.is_empty() {
                return Err("config/hf-targets contains no TOML target definitions".into());
            }
            for path in paths {
                let target_id = path
                    .file_stem()
                    .and_then(|value| value.to_str())
                    .ok_or("HF target filename is not valid UTF-8")?;
                let resolved = resolve_target(&ResolveTargetOptions {
                    repository_root: root.clone(),
                    selector: TargetSelector::Id(target_id.to_owned()),
                    runtime_variant: None,
                    targets_json: None,
                })?;
                println!(
                    "OK {}: {} -> profile_set={} -> {} / {}",
                    resolved.target_id,
                    resolved.expected_upstream_repo_id,
                    resolved.profile_set,
                    resolved.hf_model_repo,
                    resolved.hf_bucket
                );
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
