use std::collections::{BTreeMap, BTreeSet};
use std::str::FromStr;

use serde::{Deserialize, Serialize};

use crate::error::{CapsuleError, Result};

pub const EXPERIMENT_CAPSULE_SCHEMA_VERSION: &str = "experiment-capsule/v1";
pub const DEFAULT_ROW_GROUP_SIZE: usize = 512;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RecordKind {
    Manifest,
    Sample,
    Metric,
    Artifact,
    Diagnostic,
}

impl RecordKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Manifest => "manifest",
            Self::Sample => "sample",
            Self::Metric => "metric",
            Self::Artifact => "artifact",
            Self::Diagnostic => "diagnostic",
        }
    }
}

impl FromStr for RecordKind {
    type Err = CapsuleError;

    fn from_str(value: &str) -> Result<Self> {
        match value {
            "manifest" => Ok(Self::Manifest),
            "sample" => Ok(Self::Sample),
            "metric" => Ok(Self::Metric),
            "artifact" => Ok(Self::Artifact),
            "diagnostic" => Ok(Self::Diagnostic),
            other => Err(CapsuleError::Contract(format!(
                "unsupported record_kind: {other}"
            ))),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum CapsuleValue {
    String(String),
    Float64(f64),
    Int32(i32),
    Int64(i64),
    Binary(Vec<u8>),
}

#[derive(Debug, Clone, PartialEq)]
pub struct CapsuleRow {
    pub run_id: String,
    pub record_kind: RecordKind,
    pub ordinal: i64,
    fields: BTreeMap<String, CapsuleValue>,
}

impl CapsuleRow {
    pub fn new(run_id: impl Into<String>, record_kind: RecordKind, ordinal: i64) -> Result<Self> {
        let run_id = run_id.into();
        if run_id.is_empty() {
            return Err(CapsuleError::Contract("run_id must not be empty".into()));
        }
        if ordinal < 0 {
            return Err(CapsuleError::Contract(
                "ordinal must be a non-negative integer".into(),
            ));
        }
        Ok(Self {
            run_id,
            record_kind,
            ordinal,
            fields: BTreeMap::new(),
        })
    }

    pub fn with_string(mut self, name: impl Into<String>, value: impl Into<String>) -> Self {
        self.fields
            .insert(name.into(), CapsuleValue::String(value.into()));
        self
    }

    pub fn with_float64(mut self, name: impl Into<String>, value: f64) -> Self {
        self.fields
            .insert(name.into(), CapsuleValue::Float64(value));
        self
    }

    pub fn with_int32(mut self, name: impl Into<String>, value: i32) -> Self {
        self.fields.insert(name.into(), CapsuleValue::Int32(value));
        self
    }

    pub fn with_int64(mut self, name: impl Into<String>, value: i64) -> Self {
        self.fields.insert(name.into(), CapsuleValue::Int64(value));
        self
    }

    pub fn with_binary(mut self, name: impl Into<String>, value: impl Into<Vec<u8>>) -> Self {
        self.fields
            .insert(name.into(), CapsuleValue::Binary(value.into()));
        self
    }

    pub fn field(&self, name: &str) -> Option<&CapsuleValue> {
        self.fields.get(name)
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct CapsuleSummary {
    pub run_id: String,
    pub row_count: usize,
    pub sample_count: usize,
    pub diagnostic_count: usize,
    pub artifact_ids: BTreeSet<String>,
    pub metrics: BTreeMap<String, f64>,
}

impl CapsuleSummary {
    pub fn metric(&self, name: &str) -> Option<f64> {
        self.metrics.get(name).copied()
    }
}
