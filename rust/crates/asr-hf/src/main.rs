mod allocation_envelope;

use std::fs;
use std::io::{self, Read};
use std::path::PathBuf;

use allocation_envelope::{
    AllocationMetadata, AllocationResponse, allocation_request_id, read_allocation_response_id,
    write_allocation_response,
};
use asr_hf::allocation::{
    AllocationReadme, candidate_location, collection_prefix, next_sequence_id,
    write_allocation_readme,
};
use asr_hf::{ResolveTargetOptions, TargetSelector, append_github_file, resolve_target};
use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(name = "asr-hf")]
#[command(about = "Deterministic Hugging Face target, layout and allocation policy for jpapt")]
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
    AllocationPrefix {
        collection: String,
    },
    NextSequenceId {
        #[arg(long)]
        prefix: String,
        #[arg(long, default_value = "-")]
        listing: String,
    },
    ResolveCandidateLocation {
        #[arg(long, default_value = "-")]
        listing: String,
        #[arg(long)]
        candidate_id: Option<String>,
        #[arg(long)]
        runtime_variant: Option<String>,
        #[arg(long)]
        github_output: Option<PathBuf>,
    },
    WriteAllocationReadme {
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        allocation_id: String,
        #[arg(long)]
        collection: String,
        #[arg(long)]
        bucket: String,
        #[arg(long)]
        prefix: String,
        #[arg(long)]
        sequence: String,
        #[arg(long)]
        allocated_at: String,
        #[arg(long, default_value = "{}")]
        metadata_json: String,
    },
    AllocationRequestId {
        #[arg(long)]
        source_repository: Option<String>,
        #[arg(long)]
        run_id: Option<String>,
        #[arg(long)]
        run_attempt: Option<String>,
    },
    AllocationMetadata {
        #[arg(long)]
        source_repository: Option<String>,
        #[arg(long)]
        source_run_id: Option<String>,
        #[arg(long)]
        source_run_attempt: Option<String>,
        #[arg(long)]
        target_id: Option<String>,
        #[arg(long)]
        candidate_id: Option<String>,
        #[arg(long)]
        evaluation_id: Option<String>,
        #[arg(long)]
        provider_id: Option<String>,
        #[arg(long)]
        runtime_variant: Option<String>,
    },
    WriteAllocationResponse {
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        request_id: String,
        #[arg(long)]
        allocation_id: String,
        #[arg(long)]
        bucket: String,
        #[arg(long)]
        collection: String,
    },
    AllocationResponseId {
        path: PathBuf,
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
        Command::AllocationPrefix { collection } => {
            println!("{}", collection_prefix(&collection)?);
        }
        Command::NextSequenceId { prefix, listing } => {
            let content = read_listing(&listing)?;
            println!("{}", next_sequence_id(&prefix, &content)?);
        }
        Command::ResolveCandidateLocation {
            listing,
            candidate_id,
            runtime_variant,
            github_output,
        } => {
            let content = read_listing(&listing)?;
            let resolved = candidate_location(
                &content,
                candidate_id.as_deref(),
                runtime_variant.as_deref(),
            )?;
            let legacy = if resolved.legacy { "true" } else { "false" };
            let values = [
                ("candidate_id", resolved.id.as_str()),
                ("relative_path", resolved.relative_path.as_str()),
                ("legacy", legacy),
            ];
            if let Some(path) = github_output {
                append_github_file(&path, &values)?;
            }
            for (key, value) in values {
                println!("{key}={value}");
            }
        }
        Command::WriteAllocationReadme {
            output,
            allocation_id,
            collection,
            bucket,
            prefix,
            sequence,
            allocated_at,
            metadata_json,
        } => write_allocation_readme(
            output,
            &AllocationReadme {
                allocation_id: &allocation_id,
                collection: &collection,
                bucket: &bucket,
                prefix: &prefix,
                sequence: &sequence,
                allocated_at: &allocated_at,
                metadata_json: &metadata_json,
            },
        )?,
        Command::AllocationRequestId {
            source_repository,
            run_id,
            run_attempt,
        } => println!(
            "{}",
            allocation_request_id(
                source_repository.as_deref(),
                run_id.as_deref(),
                run_attempt.as_deref()
            )
        ),
        Command::AllocationMetadata {
            source_repository,
            source_run_id,
            source_run_attempt,
            target_id,
            candidate_id,
            evaluation_id,
            provider_id,
            runtime_variant,
        } => println!(
            "{}",
            AllocationMetadata {
                source_repository,
                source_run_id,
                source_run_attempt,
                target_id,
                candidate_id,
                evaluation_id,
                provider_id,
                runtime_variant,
            }
            .to_compact_json()?
        ),
        Command::WriteAllocationResponse {
            output,
            request_id,
            allocation_id,
            bucket,
            collection,
        } => write_allocation_response(
            output,
            &AllocationResponse {
                request_id: &request_id,
                allocation_id: &allocation_id,
                bucket: &bucket,
                collection: &collection,
            },
        )?,
        Command::AllocationResponseId { path } => {
            println!("{}", read_allocation_response_id(path)?);
        }
    }
    Ok(())
}

fn read_listing(listing: &str) -> Result<String, Box<dyn std::error::Error>> {
    if listing == "-" {
        let mut content = String::new();
        io::stdin().read_to_string(&mut content)?;
        Ok(content)
    } else {
        Ok(fs::read_to_string(listing)?)
    }
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
