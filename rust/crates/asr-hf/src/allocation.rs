use std::collections::BTreeSet;
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
    let maximum = maximum_collection_sequence(listing);
    let next = maximum
        .checked_add(1)
        .ok_or_else(|| contract("six-digit HF sequence space is exhausted"))?;
    if next > 999_999 {
        return Err(contract("six-digit HF sequence space is exhausted"));
    }
    Ok(format!("{prefix}-{next:06}"))
}

fn maximum_collection_sequence(listing: &str) -> u32 {
    listing
        .lines()
        .flat_map(sequence_candidates_from_path)
        .max()
        .unwrap_or(0)
}

fn sequence_candidates_from_path(raw: &str) -> Vec<u32> {
    let parts = raw
        .trim()
        .trim_start_matches('/')
        .split('/')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>();
    if parts.is_empty() {
        return Vec::new();
    }

    let mut values = Vec::with_capacity(2);
    if let Some(sequence) = sequence_suffix(parts[0].trim_end_matches('/')) {
        values.push(sequence);
    }

    // Historical Buckets placed allocation directories one level below a
    // runtime variant (for example ctc/candidate-000001 and ctc/exp-000001).
    // Count those allocation IDs so the canonical namespace never reuses a
    // historical numeric identity. Arbitrary nested artifact filenames are not
    // considered allocation IDs.
    if let Some(second) = parts.get(1)
        && is_legacy_allocation_id(second)
        && let Some(sequence) = sequence_suffix(second)
    {
        values.push(sequence);
    }
    values
}

fn is_legacy_allocation_id(value: &str) -> bool {
    ["candidate-", "exp-", "experiment-", "config-"]
        .iter()
        .any(|prefix| value.starts_with(prefix))
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

pub fn candidate_location(
    listing: &str,
    requested_id: Option<&str>,
    runtime_variant: Option<&str>,
) -> Result<CandidateLocation> {
    let requested_id = requested_id
        .map(str::trim)
        .filter(|value| !value.is_empty());
    if let Some(id) = requested_id {
        validate_candidate_id(id)?;
    }

    let requested_variant = runtime_variant
        .map(str::trim)
        .filter(|value| !value.is_empty());
    let mut canonical = BTreeSet::<String>::new();
    let mut legacy = BTreeSet::<(String, String)>::new();

    for raw in listing.lines() {
        let value = raw.trim().trim_start_matches('/');
        if value.is_empty() {
            continue;
        }
        let parts = value.split('/').collect::<Vec<_>>();
        let first = parts.first().copied().unwrap_or_default();
        if candidate_sequence(first).is_some() {
            canonical.insert(first.to_owned());
            continue;
        }
        if parts.len() >= 2 {
            let variant = first;
            let id = parts[1];
            if candidate_sequence(id).is_some() {
                legacy.insert((variant.to_owned(), id.to_owned()));
            }
        }
    }

    if let Some(id) = requested_id {
        if canonical.contains(id) {
            return Ok(CandidateLocation {
                id: id.to_owned(),
                relative_path: id.to_owned(),
                legacy: false,
            });
        }
        let matches = legacy
            .iter()
            .filter(|(variant, candidate_id)| {
                candidate_id == id
                    && requested_variant.is_none_or(|expected| variant == expected)
            })
            .collect::<Vec<_>>();
        return resolve_legacy_exact(id, requested_variant, matches);
    }

    if let Some(id) = canonical
        .iter()
        .max_by_key(|id| candidate_sequence(id).unwrap_or(0))
    {
        return Ok(CandidateLocation {
            id: id.clone(),
            relative_path: id.clone(),
            legacy: false,
        });
    }

    let candidates = legacy
        .iter()
        .filter(|(variant, _)| requested_variant.is_none_or(|expected| variant == expected))
        .collect::<Vec<_>>();
    if candidates.is_empty() {
        return Err(contract(match requested_variant {
            Some(variant) => format!(
                "bucket contains no canonical candidate-* allocation and no legacy {variant}/candidate-* allocation"
            ),
            None => "bucket contains no canonical candidate-* allocation; a runtime variant is required to resolve a legacy candidate".to_owned(),
        }));
    }
    ensure_legacy_variant_is_unambiguous(requested_variant, &candidates)?;

    let (variant, id) = candidates
        .into_iter()
        .max_by_key(|(_, id)| candidate_sequence(id).unwrap_or(0))
        .expect("non-empty candidate list");
    Ok(CandidateLocation {
        relative_path: format!("{variant}/{id}"),
        id: id.clone(),
        legacy: true,
    })
}

fn resolve_legacy_exact(
    requested_id: &str,
    requested_variant: Option<&str>,
    matches: Vec<&(String, String)>,
) -> Result<CandidateLocation> {
    if matches.is_empty() {
        return Err(contract(match requested_variant {
            Some(variant) => format!(
                "candidate {requested_id:?} was not found canonically or under legacy variant {variant:?}"
            ),
            None => format!(
                "candidate {requested_id:?} was not found canonically; provide runtime variant if it exists in a legacy layout"
            ),
        }));
    }
    ensure_legacy_variant_is_unambiguous(requested_variant, &matches)?;
    let (variant, id) = matches[0];
    Ok(CandidateLocation {
        relative_path: format!("{variant}/{id}"),
        id: id.clone(),
        legacy: true,
    })
}

fn ensure_legacy_variant_is_unambiguous(
    requested_variant: Option<&str>,
    candidates: &[&(String, String)],
) -> Result<()> {
    if requested_variant.is_some() {
        return Ok(());
    }
    let variants = candidates
        .iter()
        .map(|(variant, _)| variant.as_str())
        .collect::<BTreeSet<_>>();
    if variants.len() > 1 {
        return Err(contract(format!(
            "legacy candidate layout is ambiguous across variants {variants:?}; provide runtime variant"
        )));
    }
    Ok(())
}

fn validate_candidate_id(value: &str) -> Result<()> {
    if candidate_sequence(value).is_none() {
        return Err(contract(format!(
            "candidate id must use candidate-NNNNNN format; got {value:?}"
        )));
    }
    Ok(())
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
        "prefixはcollectionから決定されます。連番はcanonicalとhistorical layoutを合わせた最大6桁suffix + 1です。".to_owned(),
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
    fn historical_nested_ids_reserve_sequence_numbers() {
        let listing = "ctc/candidate-000004/metadata.json\ntdt/candidate-000002/metadata.json\n";
        assert_eq!(
            next_sequence_id("candidate", listing).unwrap(),
            "candidate-000005"
        );
        let experiments = "ctc/exp-000003/run.json\ntdt/exp-000001/run.json\n";
        assert_eq!(
            next_sequence_id("experiment", experiments).unwrap(),
            "experiment-000004"
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
    fn canonical_candidate_wins_over_legacy_for_latest() {
        let listing = "ctc/candidate-000009/metadata.json\ncandidate-000003/metadata.json\n";
        assert_eq!(
            candidate_location(listing, None, Some("ctc")).unwrap(),
            CandidateLocation {
                id: "candidate-000003".to_owned(),
                relative_path: "candidate-000003".to_owned(),
                legacy: false,
            }
        );
    }

    #[test]
    fn requested_legacy_candidate_is_resolved_by_variant() {
        let listing = "ctc/candidate-000001/metadata.json\ntdt/candidate-000001/metadata.json\n";
        assert_eq!(
            candidate_location(listing, Some("candidate-000001"), Some("ctc")).unwrap(),
            CandidateLocation {
                id: "candidate-000001".to_owned(),
                relative_path: "ctc/candidate-000001".to_owned(),
                legacy: true,
            }
        );
    }

    #[test]
    fn ambiguous_legacy_candidate_requires_variant() {
        let listing = "ctc/candidate-000001/metadata.json\ntdt/candidate-000001/metadata.json\n";
        assert!(candidate_location(listing, Some("candidate-000001"), None).is_err());
    }
}
