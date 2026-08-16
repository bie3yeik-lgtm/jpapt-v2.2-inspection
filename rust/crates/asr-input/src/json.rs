use std::{fs, path::Path};

use anyhow::{Context, Result, bail};
use serde::Deserialize;

use crate::model::{EVALUATION_INPUT_SCHEMA_VERSION, EvaluationInputSet, MaterializedSample};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResolvedManifestV1 {
    schema_version: u32,
    manifest_path: String,
    expected_sample_count: usize,
    resolved_sample_count: usize,
    samples: Vec<ResolvedSampleV1>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResolvedSampleV1 {
    id: String,
    manifest_entry_id: String,
    dataset_id: String,
    dataset_repo_id: String,
    dataset_revision: String,
    subset: Option<String>,
    split: Option<String>,
    row_index: usize,
    source_identity: String,
    selection_hash: String,
    selection_rank: usize,
    duration_sec: f64,
    sample_rate_hz: Option<u32>,
    transcription: String,
    #[serde(default)]
    tags: Vec<String>,
    audio_path: Option<String>,
    audio_sha256: Option<String>,
}

pub fn load_json_input(path: impl AsRef<Path>) -> Result<EvaluationInputSet> {
    let path = path.as_ref();
    let text = fs::read_to_string(path)
        .with_context(|| format!("failed to read evaluation input {}", path.display()))?;
    let value: serde_json::Value = serde_json::from_str(&text)
        .with_context(|| format!("invalid JSON evaluation input {}", path.display()))?;
    let schema_version = value
        .get("schema_version")
        .and_then(serde_json::Value::as_u64)
        .ok_or_else(|| anyhow::anyhow!("evaluation input schema_version is required"))?;

    let input = match schema_version {
        1 => normalize_v1(serde_json::from_value(value)?)?,
        version if version == u64::from(EVALUATION_INPUT_SCHEMA_VERSION) => {
            serde_json::from_value::<EvaluationInputSet>(value)?
        }
        version => bail!("unsupported JSON evaluation input schema_version {version}"),
    };
    input.validate()?;
    Ok(input)
}

fn normalize_v1(value: ResolvedManifestV1) -> Result<EvaluationInputSet> {
    if value.schema_version != 1 {
        bail!("legacy resolved manifest must use schema_version 1");
    }
    if value.expected_sample_count != value.resolved_sample_count
        || value.samples.len() != value.resolved_sample_count
    {
        bail!("legacy resolved manifest sample counts disagree");
    }

    let samples = value
        .samples
        .into_iter()
        .map(|sample| {
            let audio_path = sample
                .audio_path
                .filter(|path| !path.trim().is_empty())
                .ok_or_else(|| {
                    anyhow::anyhow!(
                        "legacy sample {} is not materialized: audio_path is required",
                        sample.id
                    )
                })?;
            let audio_sha256 = sample
                .audio_sha256
                .filter(|sha| !sha.trim().is_empty())
                .ok_or_else(|| {
                    anyhow::anyhow!(
                        "legacy sample {} is not materialized: audio_sha256 is required",
                        sample.id
                    )
                })?;
            let sample_rate_hz = sample.sample_rate_hz.ok_or_else(|| {
                anyhow::anyhow!(
                    "legacy sample {} is not materialized: sample_rate_hz is required",
                    sample.id
                )
            })?;

            Ok(MaterializedSample {
                id: sample.id,
                manifest_entry_id: sample.manifest_entry_id,
                dataset_id: sample.dataset_id,
                dataset_repo_id: sample.dataset_repo_id,
                dataset_revision: sample.dataset_revision,
                subset: sample.subset,
                split: sample.split,
                row_index: sample.row_index as u64,
                source_identity: sample.source_identity,
                selection_hash: sample.selection_hash,
                selection_rank: sample.selection_rank as u64,
                duration_sec: sample.duration_sec,
                sample_rate_hz,
                transcription: sample.transcription,
                tags: sample.tags,
                audio_path,
                audio_sha256,
            })
        })
        .collect::<Result<Vec<_>>>()?;

    Ok(EvaluationInputSet {
        schema_version: EVALUATION_INPUT_SCHEMA_VERSION,
        input_id: value.manifest_path,
        expected_sample_count: value.expected_sample_count,
        samples,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn legacy_manifest_requires_materialized_identity() {
        let value: ResolvedManifestV1 = serde_json::from_value(serde_json::json!({
            "schema_version": 1,
            "manifest_path": "fixture.json",
            "expected_sample_count": 1,
            "resolved_sample_count": 1,
            "samples": [{
                "id":"s1","manifest_entry_id":"m1","dataset_id":"d1",
                "dataset_repo_id":"org/repo","dataset_revision":"abc",
                "subset":null,"split":"test","row_index":0,
                "source_identity":"source","selection_hash":"sel",
                "selection_rank":0,"duration_sec":1.0,"sample_rate_hz":16000,
                "transcription":"test","tags":[],"audio_path":"/tmp/a.wav",
                "audio_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            }]
        })).unwrap();
        let normalized = normalize_v1(value).unwrap();
        assert_eq!(normalized.schema_version, EVALUATION_INPUT_SCHEMA_VERSION);
        assert_eq!(normalized.samples[0].sample_rate_hz, 16_000);
    }
}
