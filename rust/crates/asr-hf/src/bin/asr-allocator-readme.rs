use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const START: &str = "<!-- hf-central-allocator:start -->";
const END: &str = "<!-- hf-central-allocator:end -->";

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-allocator-readme: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut readme = None;
    let mut candidates = None;
    let mut experiments = None;
    let mut config = None;
    let mut last_id = None;
    let mut last_collection = None;
    let mut updated_at = None;

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--readme" => readme = Some(PathBuf::from(take_value(&mut args, "--readme")?)),
            "--candidates-listing" => {
                candidates = Some(PathBuf::from(take_value(
                    &mut args,
                    "--candidates-listing",
                )?))
            }
            "--experiments-listing" => {
                experiments = Some(PathBuf::from(take_value(
                    &mut args,
                    "--experiments-listing",
                )?))
            }
            "--config-listing" => {
                config = Some(PathBuf::from(take_value(&mut args, "--config-listing")?))
            }
            "--last-id" => last_id = Some(take_value(&mut args, "--last-id")?),
            "--last-collection" => {
                last_collection = Some(take_value(&mut args, "--last-collection")?)
            }
            "--updated-at" => updated_at = Some(take_value(&mut args, "--updated-at")?),
            other => return Err(format!("unsupported argument: {other}\n{}", usage())),
        }
    }

    let input = UpdateInput {
        readme: required_path(readme, "--readme")?,
        candidates_listing: required_path(candidates, "--candidates-listing")?,
        experiments_listing: required_path(experiments, "--experiments-listing")?,
        config_listing: required_path(config, "--config-listing")?,
        last_id: required_value(last_id, "--last-id")?,
        last_collection: required_value(last_collection, "--last-collection")?,
        updated_at: required_value(updated_at, "--updated-at")?,
    };
    update_readme(&input)?;
    println!("readme_path={}", input.readme.display());
    Ok(())
}

fn usage() -> &'static str {
    "usage: asr-allocator-readme --readme <README.md> --candidates-listing <file> --experiments-listing <file> --config-listing <file> --last-id <id> --last-collection <collection> --updated-at <RFC3339>"
}

#[derive(Debug)]
struct UpdateInput {
    readme: PathBuf,
    candidates_listing: PathBuf,
    experiments_listing: PathBuf,
    config_listing: PathBuf,
    last_id: String,
    last_collection: String,
    updated_at: String,
}

fn update_readme(input: &UpdateInput) -> Result<(), String> {
    for (name, value) in [
        ("last allocation ID", input.last_id.as_str()),
        ("last collection", input.last_collection.as_str()),
        ("updated_at", input.updated_at.as_str()),
    ] {
        validate_inline(name, value)?;
    }

    let candidates = current(&read_text(&input.candidates_listing)?)?;
    let experiments = current(&read_text(&input.experiments_listing)?)?;
    let config = current(&read_text(&input.config_listing)?)?;
    let existing = read_text(&input.readme)?;
    let block = render_block(input, &candidates, &experiments, &config);
    let updated = replace_managed_block(&existing, &block);
    fs::write(&input.readme, updated)
        .map_err(|error| format!("{}: {error}", input.readme.display()))
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CurrentAllocation {
    sequence: u32,
    allocation_id: String,
}

fn current(listing: &str) -> Result<CurrentAllocation, String> {
    let mut best: Option<CurrentAllocation> = None;
    for raw in listing.lines() {
        let path = raw.trim().trim_start_matches('/');
        if path.is_empty() {
            continue;
        }
        let first = path.split('/').next().unwrap_or_default();
        let Some((_, suffix)) = first.rsplit_once('-') else {
            continue;
        };
        if suffix.len() != 6 || !suffix.bytes().all(|byte| byte.is_ascii_digit()) {
            continue;
        }
        let sequence = suffix
            .parse::<u32>()
            .map_err(|error| format!("invalid allocation sequence {suffix:?}: {error}"))?;
        if best
            .as_ref()
            .is_none_or(|current| sequence > current.sequence)
        {
            best = Some(CurrentAllocation {
                sequence,
                allocation_id: first.to_owned(),
            });
        }
    }
    Ok(best.unwrap_or(CurrentAllocation {
        sequence: 0,
        allocation_id: "none".to_owned(),
    }))
}

fn render_block(
    input: &UpdateInput,
    candidates: &CurrentAllocation,
    experiments: &CurrentAllocation,
    config: &CurrentAllocation,
) -> String {
    format!(
        "{START}\n## Central Allocator 状態\n\nこの節はGitHub Actions `HF Central Sequence Allocator` が採番のたびに自動更新します。手動で番号を書き換えないでください。\n\n- 最終更新: `{}`\n- 直近の採番: `{}/{}`\n- candidates 現在番号: `{:06}`（`{}`）\n- experiments 現在番号: `{:06}`（`{}`）\n- config 現在番号: `{:06}`（`{}`）\n\n採番規則は各collectionに存在する全prefixの6桁suffixを走査し、最大値 + 1を次の番号とします。複数Repositoryからの採番要求も中央Allocator RepositoryでBucket単位に直列化されます。\n{END}",
        input.updated_at,
        input.last_collection,
        input.last_id,
        candidates.sequence,
        candidates.allocation_id,
        experiments.sequence,
        experiments.allocation_id,
        config.sequence,
        config.allocation_id,
    )
}

fn replace_managed_block(existing: &str, block: &str) -> String {
    if let (Some(start), Some(end)) = (existing.find(START), existing.find(END))
        && start < end
    {
        let before = existing[..start].trim_end();
        let after = &existing[end + END.len()..];
        return format!("{before}\n\n{block}{after}");
    }
    let before = existing.trim_end();
    if before.is_empty() {
        format!("{block}\n")
    } else {
        format!("{before}\n\n{block}\n")
    }
}

fn read_text(path: &Path) -> Result<String, String> {
    fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))
}

fn validate_inline(name: &str, value: &str) -> Result<(), String> {
    if value.trim().is_empty() {
        return Err(format!("{name} must be a non-empty string"));
    }
    if value.contains(['\n', '\r', '`']) {
        return Err(format!(
            "{name} contains an unsafe inline Markdown character"
        ));
    }
    Ok(())
}

fn required_path(value: Option<PathBuf>, option: &str) -> Result<PathBuf, String> {
    value.ok_or_else(|| format!("{option} is required"))
}

fn required_value(value: Option<String>, option: &str) -> Result<String, String> {
    value.ok_or_else(|| format!("{option} is required"))
}

fn take_value(args: &mut impl Iterator<Item = String>, option: &str) -> Result<String, String> {
    args.next()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{option} requires a non-empty value"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn current_uses_maximum_suffix_across_prefixes() {
        let listing = "whisper-000003/file\nctc-000009/model\nignored.txt\n";
        assert_eq!(
            current(listing).unwrap(),
            CurrentAllocation {
                sequence: 9,
                allocation_id: "ctc-000009".to_owned(),
            }
        );
    }

    #[test]
    fn zero_suffix_is_a_real_allocation() {
        assert_eq!(
            current("candidate-000000/file\n").unwrap(),
            CurrentAllocation {
                sequence: 0,
                allocation_id: "candidate-000000".to_owned(),
            }
        );
    }

    #[test]
    fn empty_listing_reports_zero_and_none() {
        assert_eq!(
            current("").unwrap(),
            CurrentAllocation {
                sequence: 0,
                allocation_id: "none".to_owned(),
            }
        );
    }

    #[test]
    fn managed_block_replacement_preserves_human_content() {
        let existing = format!("# Bucket\n\nHuman\n\n{START}\nold\n{END}\n\nTail\n");
        let updated = replace_managed_block(&existing, "BLOCK");
        assert_eq!(updated, "# Bucket\n\nHuman\n\nBLOCK\n\nTail\n");
    }

    #[test]
    fn missing_block_appends_once() {
        assert_eq!(
            replace_managed_block("# Bucket\n", "BLOCK"),
            "# Bucket\n\nBLOCK\n"
        );
    }
}
