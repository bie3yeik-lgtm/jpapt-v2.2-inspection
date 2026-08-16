use std::fs;
use std::path::Path;

use serde_json::Value;

use crate::{HfError, Result};

pub fn collection_prefix(collection: &str) -> Result<&'static str> {
    match collection {
        "candidates" => Ok("candidate"),
        "experiments" => Ok("experiment"),
        "config" => Ok("config"),
        other => Err(contract(format!(
            "allocation collection must be candidates, experiments, or config; got {other:?}"
        ))),
    }
}

pub fn next_sequence_id(prefix: &str, listing: &str) -> Result<String> {
    validate_prefix(prefix)?;
    let maximum = maximum_root_sequence(listing);
    let next = maximum
        .checked_add(1)
        .ok_or_else(|| contract("six-digit HF sequence space is exhausted"))?;
    if next > 999_999 {
        return Err(contract("six-digit HF sequence space is exhausted"));
    }
    Ok(format!("{prefix}-{next:06}"))
}

fn maximum_root_sequence(listing: &str) -> u32 {
    listing
        .lines()
        .filter_map(|raw| {
            let root = raw.trim().split('/').next()?.trim_end_matches('/');
            sequence_suffix(root)
        })
        .max()
        .unwrap_or(0)
}

fn sequence_suffix(value: &str) -> Option<u32> {
    let (_, suffix) = value.rsplit_once('-')?;
    if suffix.len() != 6 || !suffix.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    suffix.parse().ok()
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CandidateLocation {
    pub id: String,
    pub relative_path: String,
    pub legacy: bool,
}

pub fn latest_candidate_location(
    listing: &str,
    runtime_variant: Option<&str>,
) -> Result<CandidateLocation> {
    let mut canonical = Vec::<(u32, String)>::new();
    let mut legacy = Vec::<(u32, String, String)>::new();

    for raw in listing.lines() {
        let value = raw.trim().trim_start_matches('/');
        if value.is_empty() {
            continue;
        }
        let parts = value.split('/').collect::<Vec<_>>();
        let first = parts.first().copied().unwrap_or_default();
        if let Some(sequence) = candidate_sequence(first) {
            canonical.push((sequence, first.to_owned()));
            continue;
        }
        if parts.len() >= 2 {
            let variant = first;
            let id = parts[1];
            if let Some(sequence) = candidate_sequence(id) {
                legacy.push((sequence, variant.to_owned(), id.to_owned()));
            }
        }
    }

    if let Some((_, id)) = canonical.into_iter().max_by_key(|(sequence, _)| *sequence) {
        return Ok(CandidateLocation {
            relative_path: id.clone(),
            id,
            legacy: false,
        });
    }

    let requested_variant = runtime_variant
        .map(str::trim)
        .filter(|value| !value.is_empty());
    let candidates = legacy
        .into_iter()
        .filter(|(_, variant, _)| requested_variant.is_none_or(|expected| variant == expected))
        .collect::<Vec<_>>();

    if candidates.is_empty() {
        return Err(contract(match requested_variant {
            Some(variant) => format!(
                "bucket contains no canonical candidate-* allocation and no legacy {variant}/candidate-* allocation"
            ),
            None => "bucket contains no canonical candidate-* allocation; a runtime variant is required to resolve a legacy candidate".to_owned(),
        }));
    }

    if requested_variant.is_none() {
        let variants = candidates
            .iter()
            .map(|(_, variant, _)| variant.as_str())
            .collect::<std::collections::BTreeSet<_>>();
        if variants.len() > 1 {
            return Err(contract(format!(
                "legacy candidate layout is ambiguous across variants {variants:?}; provide runtime variant"
            )));
        }
    }

    let (_, variant, id) = candidates
        .into_iter()
        .max_by_key(|(sequence, _, _)| *sequence)
        .expect("non-empty candidate list");
    Ok(CandidateLocation {
        relative_path: format!("{variant}/{id}"),
        id,
        legacy: true,
    })
}

fn candidate_sequence(value: &str) -> Option<u32> {
    if !value.starts_with("candidate-") {
        return None;
    }
    sequence_suffix(value)
}

#[derive(Debug, Clone)]
pub struct AllocationReadme<'a> {
    pub allocation_id: &'a str,
    pub collection: &'a str,
    pub bucket: &'a str,
    pub prefix: &'a str,
    pub sequence: &'a str,
    pub allocated_at: &'a str,
    pub metadata_json: &'a str,
}

pub fn write_allocation_readme(
    output: impl AsRef<Path>,
    input: &AllocationReadme<'_>,
) -> Result<()> {
    validate_prefix(input.prefix)?;
    let expected_prefix = collection_prefix(input.collection)?;
    if input.prefix != expected_prefix {
        return Err(contract(format!(
            "collection {:?} must use derived prefix {:?}, got {:?}",
            input.collection, expected_prefix, input.prefix
        )));
    }
    for (name, value) in [
        ("allocation_id", input.allocation_id),
        ("bucket", input.bucket),
        ("sequence", input.sequence),
        ("allocated_at", input.allocated_at),
    ] {
        if value.trim().is_empty() {
            return Err(contract(format!("{name} must be a non-empty string")));
        }
    }
    let metadata: Value = serde_json::from_str(input.metadata_json)?;
    let object = metadata
        .as_object()
        .ok_or_else(|| contract("HF_ALLOCATION_METADATA_JSON must be a JSON object"))?;

    let mut lines = vec![
        format!("# {}", input.allocation_id),
        String::new(),
        "このディレクトリIDは中央Allocatorが自動採番しました。数値suffixは手動で再利用・変更しないでください。".to_owned(),
        String::new(),
        format!("- collection: `{}`", input.collection),
        format!("- bucket: `{}`", input.bucket),
        format!("- prefix: `{}`", input.prefix),
        format!("- sequence: `{}`", input.sequence),
        format!("- allocated_at: `{}`", input.allocated_at),
    ];
    let mut keys = object.keys().collect::<Vec<_>>();
    keys.sort();
    for key in keys {
        let value = &object[key];
        if value.is_null() || value.as_str().is_some_and(str::is_empty) {
            continue;
        }
        let rendered = match value {
            Value::String(value) => value.clone(),
            _ => serde_json::to_string(value)?,
        };
        lines.push(format!("- {key}: `{rendered}`"));
    }
    lines.extend([
        String::new(),
        "prefixはcollectionから決定されます。連番はcollection全体の最大6桁suffix + 1です。".to_owned(),
        "新規allocationはcanonical layoutへだけ書き込み、variant配下の旧candidate layoutは読み取りfallbackに限定されます。".to_owned(),
    ]);
    let path = output.as_ref().to_path_buf();
    fs::write(&path, format!("{}\n", lines.join("\n")))
        .map_err(|source| HfError::Io { path, source })
}

fn validate_prefix(prefix: &str) -> Result<()> {
    let bytes = prefix.as_bytes();
    if bytes.is_empty()
        || !bytes[0].is_ascii_alphanumeric()
        || !bytes[bytes.len() - 1].is_ascii_alphanumeric()
        || !bytes.iter().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'_' | b'-')
        })
    {
        return Err(contract(
            "prefix must contain only lowercase ASCII letters, digits, '.', '_', or '-', and must start/end with an alphanumeric character",
        ));
    }
    Ok(())
}

fn contract(message: impl Into<String>) -> HfError {
    HfError::Contract(message.into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collection_prefix_is_derived() {
        assert_eq!(collection_prefix("candidates").unwrap(), "candidate");
        assert_eq!(collection_prefix("experiments").unwrap(), "experiment");
        assert_eq!(collection_prefix("config").unwrap(), "config");
        assert!(collection_prefix("runs").is_err());
    }

    #[test]
    fn empty_collection_starts_at_one() {
        assert_eq!(next_sequence_id("candidate", "").unwrap(), "candidate-000001");
    }

    #[test]
    fn prefixes_share_collection_sequence() {
        let listing = "old-prefix-000001/README.md\ncandidate-000004/README.md\nexperiment-000003/README.md\n";
        assert_eq!(
            next_sequence_id("candidate", listing).unwrap(),
            "candidate-000005"
        );
    }

    #[test]
    fn nested_numeric_filenames_do_not_influence_sequence() {
        let listing = "candidate-000002/logs/output-999999.txt\ncandidate-000002/artifacts/model-888888.onnx\n";
        assert_eq!(
            next_sequence_id("candidate", listing).unwrap(),
            "candidate-000003"
        );
    }

    #[test]
    fn canonical_candidate_wins_over_legacy() {
        let listing = "ctc/candidate-000009/metadata.json\ncandidate-000003/metadata.json\n";
        assert_eq!(
            latest_candidate_location(listing, Some("ctc")).unwrap(),
            CandidateLocation {
                id: "candidate-000003".to_owned(),
                relative_path: "candidate-000003".to_owned(),
                legacy: false,
            }
        );
    }

    #[test]
    fn legacy_candidate_is_variant_scoped() {
        let listing = "ctc/candidate-000001/metadata.json\ntdt/candidate-000004/metadata.json\nctc/candidate-000003/metadata.json\n";
        assert_eq!(
            latest_candidate_location(listing, Some("ctc")).unwrap(),
            CandidateLocation {
                id: "candidate-000003".to_owned(),
                relative_path: "ctc/candidate-000003".to_owned(),
                legacy: true,
            }
        );
    }

    #[test]
    fn ambiguous_legacy_candidate_requires_variant() {
        let listing = "ctc/candidate-000001/metadata.json\ntdt/candidate-000002/metadata.json\n";
        assert!(latest_candidate_location(listing, None).is_err());
    }
}
