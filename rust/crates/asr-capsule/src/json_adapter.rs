use serde_json::{Map, Value};

use crate::error::{CapsuleError, Result};
use crate::model::{CapsuleRow, RecordKind};

fn required_str<'a>(value: &'a Value, pointer: &str) -> Result<&'a str> {
    value
        .pointer(pointer)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| CapsuleError::Contract(format!("required string is missing: {pointer}")))
}

fn optional_str<'a>(value: &'a Value, pointer: &str) -> Option<&'a str> {
    value.pointer(pointer).and_then(Value::as_str)
}

fn optional_f64(value: &Value, pointer: &str) -> Option<f64> {
    value.pointer(pointer).and_then(Value::as_f64)
}

fn optional_i64(value: &Value, pointer: &str) -> Option<i64> {
    value.pointer(pointer).and_then(Value::as_i64)
}

fn json(value: Value) -> Result<String> {
    Ok(serde_json::to_string(&value)?)
}

fn set_optional_string(mut row: CapsuleRow, name: &str, value: Option<&str>) -> CapsuleRow {
    if let Some(value) = value {
        row = row.with_string(name, value);
    }
    row
}

fn set_optional_float(mut row: CapsuleRow, name: &str, value: Option<f64>) -> CapsuleRow {
    if let Some(value) = value {
        row = row.with_float64(name, value);
    }
    row
}

fn sample_row(value: &Value, run_id: &str, ordinal: i64) -> Result<CapsuleRow> {
    if required_str(value, "/run_id")? != run_id {
        return Err(CapsuleError::Contract(
            "sample result run_id does not match capsule run_id".into(),
        ));
    }

    let mut row = CapsuleRow::new(run_id, RecordKind::Sample, ordinal)?
        .with_string("sample_id", required_str(value, "/sample/id")?)
        .with_string("dataset_id", required_str(value, "/sample/dataset_id")?)
        .with_string(
            "dataset_repo_id",
            required_str(value, "/sample/dataset_repo_id")?,
        )
        .with_string(
            "dataset_revision",
            required_str(value, "/sample/dataset_revision")?,
        )
        .with_float64(
            "audio_duration_sec",
            optional_f64(value, "/sample/audio_duration_sec").ok_or_else(|| {
                CapsuleError::Contract("sample audio_duration_sec is missing".into())
            })?,
        )
        .with_int32(
            "sample_rate_hz",
            i32::try_from(
                optional_i64(value, "/sample/sample_rate_hz").ok_or_else(|| {
                    CapsuleError::Contract("sample sample_rate_hz is missing".into())
                })?,
            )
            .map_err(|_| CapsuleError::Contract("sample_rate_hz is out of range".into()))?,
        )
        .with_string(
            "reference_text",
            required_str(value, "/sample/reference_text")?,
        )
        .with_string("hypothesis_text", required_str(value, "/output/text")?)
        .with_string(
            "normalized_text",
            required_str(value, "/output/normalized_text")?,
        )
        .with_string(
            "provider_id",
            required_str(value, "/execution/provider_id")?,
        )
        .with_string("decoder", required_str(value, "/execution/decoder")?)
        .with_string("status", required_str(value, "/status")?);

    for (name, pointer) in [
        ("subset", "/sample/subset"),
        ("split", "/sample/split"),
        ("audio_sha256", "/sample/audio_sha256"),
    ] {
        row = set_optional_string(row, name, optional_str(value, pointer));
    }

    for (name, pointer) in [
        ("cer", "/quality/cer"),
        ("wer", "/quality/wer"),
        ("load_ms", "/timing/load_ms"),
        ("session_creation_ms", "/timing/session_creation_ms"),
        ("audio_decode_ms", "/timing/audio_decode_ms"),
        ("resample_ms", "/timing/resample_ms"),
        ("frontend_ms", "/timing/frontend_ms"),
        ("encoder_ms", "/timing/encoder_ms"),
        ("inference_ms", "/timing/inference_ms"),
        ("decoder_ms", "/timing/decoder_ms"),
        ("postprocess_ms", "/timing/postprocess_ms"),
        ("total_ms", "/timing/total_ms"),
        ("rtf", "/timing/rtf"),
        ("peak_ram_mb", "/memory/peak_ram_mb"),
        ("peak_device_memory_mb", "/memory/peak_device_memory_mb"),
    ] {
        row = set_optional_float(row, name, optional_f64(value, pointer));
    }

    let first_error = value
        .pointer("/errors/0")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    for (name, key) in [
        ("error_code", "code"),
        ("error_stage", "stage"),
        ("error_message", "message"),
    ] {
        row = set_optional_string(row, name, first_error.get(key).and_then(Value::as_str));
    }

    let mut metadata = Map::new();
    metadata.insert(
        "sample_index".into(),
        value
            .pointer("/sample/index")
            .cloned()
            .unwrap_or(Value::Null),
    );
    for (name, pointer) in [
        ("execution", "/execution"),
        ("tokens", "/output/tokens"),
        ("token_count", "/output/token_count"),
        ("parity", "/parity"),
        ("provider", "/provider"),
        ("errors", "/errors"),
    ] {
        metadata.insert(
            name.into(),
            value.pointer(pointer).cloned().unwrap_or(Value::Null),
        );
    }
    Ok(row.with_string("metadata_json", json(Value::Object(metadata))?))
}

fn metric_unit(name: &str) -> Option<&'static str> {
    if name.ends_with("_ms") {
        Some("ms")
    } else if name.ends_with("_sec") {
        Some("s")
    } else if name.ends_with("_mb") {
        Some("MB")
    } else if name.ends_with("_bytes") {
        Some("bytes")
    } else {
        None
    }
}

fn collect_metrics(prefix: &str, value: &Value, output: &mut Vec<(String, f64)>) {
    let Some(object) = value.as_object() else {
        return;
    };
    let mut keys = object.keys().collect::<Vec<_>>();
    keys.sort();
    for key in keys {
        let item = &object[key];
        let name = if prefix.is_empty() {
            key.to_owned()
        } else {
            format!("{prefix}.{key}")
        };
        if item.is_object() {
            collect_metrics(&name, item, output);
        } else if !item.is_boolean() && !item.is_null() {
            if let Some(number) = item.as_f64() {
                output.push((name, number));
            }
        }
    }
}

pub fn rows_from_evaluation_json(
    run_context: &Value,
    samples: &[Value],
    benchmark: &Value,
) -> Result<Vec<CapsuleRow>> {
    let run_id = required_str(run_context, "/run_id")?;
    if required_str(benchmark, "/run_id")? != run_id {
        return Err(CapsuleError::Contract(
            "benchmark run_id does not match run_context run_id".into(),
        ));
    }

    let manifest_metadata = serde_json::json!({
        "run_context": run_context,
        "benchmark": benchmark,
    });
    let mut rows = vec![
        CapsuleRow::new(run_id, RecordKind::Manifest, 0)?
            .with_string("name", "run")
            .with_string("category", "evaluation")
            .with_string("metadata_json", json(manifest_metadata)?),
    ];

    let mut ordinal = 1i64;
    for sample in samples {
        rows.push(sample_row(sample, run_id, ordinal)?);
        ordinal += 1;
    }

    for section in [
        "samples",
        "quality",
        "performance",
        "memory",
        "parity",
        "provider",
        "errors",
    ] {
        let Some(section_value) = benchmark.get(section) else {
            continue;
        };
        let mut metrics = Vec::new();
        collect_metrics(section, section_value, &mut metrics);
        for (name, value) in metrics {
            let mut row = CapsuleRow::new(run_id, RecordKind::Metric, ordinal)?
                .with_string("metric_name", &name)
                .with_float64("metric_value", value);
            if let Some(unit) = metric_unit(name.rsplit('.').next().unwrap_or(&name)) {
                row = row.with_string("metric_unit", unit);
            }
            rows.push(row);
            ordinal += 1;
        }
    }

    Ok(rows)
}
