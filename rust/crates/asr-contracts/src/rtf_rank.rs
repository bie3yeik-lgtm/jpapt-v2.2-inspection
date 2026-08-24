use std::cmp::Ordering;

use serde::Serialize;
use serde_json::Value;

use crate::{ContractError, Result, validate_rtf_benchmark_record};

const IDENTITY_FIELDS: &[&str] = &[
    "phase",
    "model_id",
    "decoder",
    "dataset_manifest_id",
    "dataset_manifest_sha256",
    "dataset_revision",
    "fixture_repo_id",
    "fixture_revision",
    "image_digest",
    "precision",
];

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct RtfRankExclusion {
    pub input: String,
    pub run_id: Option<String>,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct RtfRankOutput {
    pub schema_version: u32,
    pub records: Vec<Value>,
    pub excluded: Vec<RtfRankExclusion>,
}

pub fn rank_rtf_records(
    inputs: impl IntoIterator<Item = (String, Value)>,
    expected_phase: Option<&str>,
) -> Result<RtfRankOutput> {
    let mut candidates = Vec::new();
    let mut excluded = Vec::new();
    let mut identity: Option<Value> = None;
    let mut seen = std::collections::BTreeSet::new();

    for (input, value) in inputs {
        let run_id = value["run_id"].as_str().map(str::to_owned);
        if value["status"] != "completed" {
            excluded.push(RtfRankExclusion {
                input,
                run_id,
                reason: "status is not completed".to_owned(),
            });
            continue;
        }
        if let Err(error) = validate_rtf_benchmark_record(&value) {
            excluded.push(RtfRankExclusion {
                input,
                run_id,
                reason: format!("invalid benchmark record: {error}"),
            });
            continue;
        }
        if let Some(phase) = expected_phase
            && value["phase"].as_str() != Some(phase)
        {
            return Err(ContractError::validation(format!(
                "{input}: phase does not match requested ranking phase {phase:?}"
            )));
        }
        if value["provider_execution_proof"] != true {
            excluded.push(RtfRankExclusion {
                input,
                run_id,
                reason: "provider execution proof is false".to_owned(),
            });
            continue;
        }
        if value["cer"].is_null() {
            excluded.push(RtfRankExclusion {
                input,
                run_id,
                reason: "CER is missing".to_owned(),
            });
            continue;
        }
        if value["cost_per_audio_hour"].is_null() {
            excluded.push(RtfRankExclusion {
                input,
                run_id,
                reason: "cost_per_audio_hour is missing".to_owned(),
            });
            continue;
        }

        candidates.push((input, value));
    }

    if candidates.is_empty() {
        return Err(ContractError::validation(
            "no accepted completed benchmark records are available for ranking",
        ));
    }
    // Keep the newest valid metrics for each benchmark machine/cell. Batch size
    // remains part of the key because smoke ranking compares batch 1/8/32.
    let mut latest_by_cell = std::collections::BTreeMap::<String, (String, Value)>::new();
    for (input, value) in candidates {
        let cell = format!(
            "{}\u{1f}{}\u{1f}{}",
            value["service_id"], value["gpu"], value["batch_size"]
        );
        let candidate_key = recency_key(&value, &input);
        if let Some((previous_input, previous_value)) = latest_by_cell.get(&cell) {
            if candidate_key <= recency_key(previous_value, previous_input) {
                excluded.push(RtfRankExclusion {
                    input,
                    run_id: value["run_id"].as_str().map(str::to_owned),
                    reason: "older completed record superseded by a newer complete record"
                        .to_owned(),
                });
                continue;
            }
            excluded.push(RtfRankExclusion {
                input: previous_input.clone(),
                run_id: previous_value["run_id"].as_str().map(str::to_owned),
                reason: "older completed record superseded by a newer complete record".to_owned(),
            });
        }
        latest_by_cell.insert(cell, (input, value));
    }
    let mut accepted: Vec<Value> = latest_by_cell
        .into_values()
        .map(|(_, value)| value)
        .collect();
    for value in &accepted {
        let identity_value = identity_value(value)?;
        if let Some(expected) = &identity
            && expected != &identity_value
        {
            return Err(ContractError::validation(
                "accepted record identity does not match the ranking set",
            ));
        }
        identity.get_or_insert(identity_value);
        let duplicate_key = format!(
            "{}\u{1f}{}\u{1f}{}\u{1f}{}",
            value["run_id"], value["service_id"], value["gpu"], value["batch_size"]
        );
        if !seen.insert(duplicate_key) {
            return Err(ContractError::validation(
                "duplicate accepted run/service/gpu/batch record",
            ));
        }
    }
    accepted.sort_by(|left, right| {
        compare_number(left, right, "cost_per_audio_hour")
            .then_with(|| compare_number(left, right, "cer"))
            .then_with(|| compare_number(left, right, "rtf"))
            .then_with(|| {
                left["service_id"]
                    .as_str()
                    .cmp(&right["service_id"].as_str())
            })
            .then_with(|| left["gpu"].as_str().cmp(&right["gpu"].as_str()))
            .then_with(|| {
                left["batch_size"]
                    .as_u64()
                    .cmp(&right["batch_size"].as_u64())
            })
            .then_with(|| left["run_id"].as_str().cmp(&right["run_id"].as_str()))
    });
    Ok(RtfRankOutput {
        schema_version: 1,
        records: accepted,
        excluded,
    })
}

fn recency_key(value: &Value, input: &str) -> (String, String) {
    (
        value["completed_at"]
            .as_str()
            .or_else(|| value["run_id"].as_str())
            .unwrap_or_default()
            .to_owned(),
        input.to_owned(),
    )
}

fn identity_value(value: &Value) -> Result<Value> {
    let object = value
        .as_object()
        .ok_or_else(|| ContractError::validation("benchmark record must be an object"))?;
    let mut identity = serde_json::Map::new();
    for field in IDENTITY_FIELDS {
        identity.insert(
            (*field).to_owned(),
            object.get(*field).cloned().ok_or_else(|| {
                ContractError::validation(format!("missing identity field {field}"))
            })?,
        );
    }
    Ok(Value::Object(identity))
}

fn compare_number(left: &Value, right: &Value, key: &str) -> Ordering {
    left[key]
        .as_f64()
        .partial_cmp(&right[key].as_f64())
        .unwrap_or(Ordering::Equal)
}

#[cfg(test)]
mod tests {
    use super::rank_rtf_records;
    use serde_json::json;

    fn record(run_id: &str, cost: Option<f64>, cer: Option<f64>) -> serde_json::Value {
        json!({
            "schema_version": 1, "run_id": run_id, "phase": "phase1", "service_id": "hf-jobs", "gpu": "t4", "model_id": "model", "decoder": "tdt",
            "dataset_manifest_id": "benchmark-v1", "dataset_manifest_sha256": "a".repeat(64), "dataset_revision": "dataset", "fixture_repo_id": "gawohok7/rtf-benchmark-fixtures", "fixture_revision": "b".repeat(40), "image_digest": format!("sha256:{}", "c".repeat(64)),
            "batch_size": 1, "repeat": 1, "precision": "float16", "status": "completed", "provider_execution_proof": true,
            "audio_duration_sec": 10.0, "processing_duration_sec": 1.0, "rtf": 0.1, "rtfx": 10.0, "rtf_scope": "service", "cer": cer, "wer": null,
            "peak_vram_mb": 1.0, "gpu_utilization_percent": 1.0, "gpu_price_per_hour": 1.0, "cost_per_audio_hour": cost,
            "metrics_uri": "https://example.invalid/metrics.json", "metrics_sha256": "d".repeat(64)
        })
    }

    #[test]
    fn rejects_empty_accepted_set() {
        let result = rank_rtf_records(
            vec![("blocked.json".to_owned(), record("run", None, None))],
            Some("phase1"),
        );
        assert!(result.is_err());
    }

    #[test]
    fn records_exclusions_and_sorts_accepted_records() {
        let mut second = record("run-2", Some(0.2), Some(0.2));
        second["batch_size"] = json!(2);
        let result = rank_rtf_records(
            vec![
                ("run-2.json".to_owned(), second),
                (
                    "run-1.json".to_owned(),
                    record("run-1", Some(0.1), Some(0.3)),
                ),
            ],
            Some("phase1"),
        )
        .expect("ranking should succeed");
        assert_eq!(result.records[0]["run_id"], "run-1");
        assert!(result.excluded.is_empty());
    }

    #[test]
    fn selects_latest_complete_record_per_cell() {
        let mut older = record("run-old", Some(0.2), Some(0.2));
        older["completed_at"] = json!("2026-08-24T00:00:00Z");
        let mut newer = record("run-new", Some(0.1), Some(0.1));
        newer["completed_at"] = json!("2026-08-24T01:00:00Z");
        let result = rank_rtf_records(
            vec![
                ("old.json".to_owned(), older),
                ("new.json".to_owned(), newer),
            ],
            Some("phase1"),
        )
        .expect("latest complete record should be ranked");
        assert_eq!(result.records.len(), 1);
        assert_eq!(result.records[0]["run_id"], "run-new");
        assert_eq!(result.excluded.len(), 1);
        assert!(result.excluded[0].reason.contains("superseded"));
    }

    #[test]
    fn ignores_newer_blocked_record_when_complete_record_exists() {
        let complete = record("run-complete", Some(0.1), Some(0.1));
        let blocked = json!({
            "run_id": "run-blocked", "status": "blocked", "service_id": "hf-jobs",
            "gpu": "t4", "batch_size": 1
        });
        let result = rank_rtf_records(
            vec![
                ("complete.json".to_owned(), complete),
                ("blocked.json".to_owned(), blocked),
            ],
            Some("phase1"),
        )
        .expect("blocked latest attempt must not hide complete data");
        assert_eq!(result.records.len(), 1);
        assert_eq!(result.records[0]["run_id"], "run-complete");
        assert_eq!(result.excluded[0].reason, "status is not completed");
    }

    #[test]
    fn excludes_invalid_completed_record_and_keeps_valid_machine() {
        let valid = record("run-valid", Some(0.1), Some(0.1));
        let invalid = json!({
            "run_id": "run-invalid", "status": "completed", "service_id": "hf-jobs",
            "gpu": "t4", "batch_size": 1
        });
        let result = rank_rtf_records(
            vec![
                ("invalid.json".to_owned(), invalid),
                ("valid.json".to_owned(), valid),
            ],
            Some("phase1"),
        )
        .expect("invalid record should be excluded while valid data remains");
        assert_eq!(result.records.len(), 1);
        assert_eq!(result.records[0]["run_id"], "run-valid");
        assert!(
            result.excluded[0]
                .reason
                .starts_with("invalid benchmark record:")
        );
    }
}
