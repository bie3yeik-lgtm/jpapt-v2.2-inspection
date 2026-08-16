use std::{
    path::{Path, PathBuf},
    time::Instant,
};

use ort::{
    session::{builder::GraphOptimizationLevel, Session},
    value::TensorRef,
};

use crate::{
    metadata::model_metadata::CtcRuntimeContract,
    providers::{self, ProviderKind},
    Result, RuntimeError,
};

#[derive(Debug, Clone)]
pub struct SessionTuning {
    pub graph_optimization_level: GraphOptimizationLevel,
    pub parallel_execution: bool,
    pub memory_pattern: bool,
    pub intra_threads: Option<usize>,
    pub inter_threads: Option<usize>,
    pub allow_cpu_fallback: bool,
}

impl Default for SessionTuning {
    fn default() -> Self {
        Self {
            graph_optimization_level: GraphOptimizationLevel::All,
            parallel_execution: false,
            memory_pattern: true,
            intra_threads: None,
            inter_threads: None,
            allow_cpu_fallback: true,
        }
    }
}

impl SessionTuning {
    pub fn from_run_context(value: &serde_json::Value) -> Result<Self> {
        let mut tuning = Self::default();
        if let Some(level) = value
            .pointer("/config/resolved/provider/session/graph_optimization_level")
            .and_then(serde_json::Value::as_str)
        {
            tuning.graph_optimization_level = match level {
                "disable" | "disabled" | "none" => GraphOptimizationLevel::Disable,
                "level1" | "basic" => GraphOptimizationLevel::Level1,
                "level2" | "extended" => GraphOptimizationLevel::Level2,
                "level3" | "layout" => GraphOptimizationLevel::Level3,
                "all" => GraphOptimizationLevel::All,
                other => {
                    return Err(RuntimeError::InvalidMetadata(format!(
                        "unsupported graph_optimization_level {other:?}"
                    )))
                }
            };
        }
        if let Some(mode) = value
            .pointer("/config/resolved/provider/session/execution_mode")
            .and_then(serde_json::Value::as_str)
        {
            tuning.parallel_execution = match mode {
                "sequential" => false,
                "parallel" => true,
                other => {
                    return Err(RuntimeError::InvalidMetadata(format!(
                        "unsupported execution_mode {other:?}"
                    )))
                }
            };
        }
        if let Some(enabled) = value
            .pointer("/config/resolved/provider/session/enable_mem_pattern")
            .and_then(serde_json::Value::as_bool)
        {
            tuning.memory_pattern = enabled;
        }
        tuning.intra_threads = positive_usize(
            value.pointer("/config/resolved/environment/runtime/cpu/intra_op_threads"),
        );
        tuning.inter_threads = positive_usize(
            value.pointer("/config/resolved/environment/runtime/cpu/inter_op_threads"),
        );
        if let Some(allow) = value
            .pointer("/config/resolved/provider/validation/allow_cpu_fallback")
            .and_then(serde_json::Value::as_bool)
        {
            tuning.allow_cpu_fallback = allow;
        }
        if value
            .pointer("/config/resolved/provider/validation/strict_provider_mode")
            .and_then(serde_json::Value::as_bool)
            == Some(true)
        {
            tuning.allow_cpu_fallback = false;
        }
        Ok(tuning)
    }
}

fn positive_usize(value: Option<&serde_json::Value>) -> Option<usize> {
    value
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .filter(|value| *value > 0)
}

#[derive(Debug, Clone)]
pub struct SessionConfig {
    pub model_path: PathBuf,
    pub provider: ProviderKind,
    pub tuning: SessionTuning,
}

impl SessionConfig {
    pub fn new(
        model_path: impl AsRef<Path>,
        provider: ProviderKind,
        tuning: SessionTuning,
    ) -> Self {
        Self {
            model_path: model_path.as_ref().to_path_buf(),
            provider,
            tuning,
        }
    }
}

#[derive(Debug, Clone)]
pub struct InferenceOutput {
    pub token_ids: Vec<i64>,
    pub inference_ms: f64,
}

pub struct OrtCtcSession {
    session: Session,
    contract: CtcRuntimeContract,
    provider: ProviderKind,
    session_creation_ms: f64,
    cpu_fallback_allowed: bool,
}

impl OrtCtcSession {
    pub fn create(config: SessionConfig, contract: CtcRuntimeContract) -> Result<Self> {
        if !config.model_path.is_file() {
            return Err(RuntimeError::ModelMissing(config.model_path));
        }

        let started = Instant::now();
        let mut builder = Session::builder()?
            .with_optimization_level(config.tuning.graph_optimization_level)
            .map_err(builder_error)?
            .with_parallel_execution(config.tuning.parallel_execution)
            .map_err(builder_error)?
            .with_memory_pattern(config.tuning.memory_pattern)
            .map_err(builder_error)?;
        if !config.tuning.allow_cpu_fallback {
            builder = builder
                .with_disable_cpu_fallback()
                .map_err(builder_error)?;
        }
        if let Some(threads) = config.tuning.intra_threads {
            builder = builder.with_intra_threads(threads).map_err(builder_error)?;
        }
        if let Some(threads) = config.tuning.inter_threads {
            builder = builder.with_inter_threads(threads).map_err(builder_error)?;
        }
        builder = providers::configure(builder, config.provider)?;
        let session = builder.commit_from_file(&config.model_path)?;
        let session_creation_ms = started.elapsed().as_secs_f64() * 1000.0;

        let inputs: Vec<&str> = session.inputs().iter().map(|input| input.name()).collect();
        if !inputs.iter().any(|name| *name == contract.primary_input) {
            return Err(RuntimeError::InvalidMetadata(format!(
                "primary input '{}' not found in model inputs {inputs:?}",
                contract.primary_input
            )));
        }
        if let Some(length) = &contract.length_input {
            if !inputs.iter().any(|name| *name == length) {
                return Err(RuntimeError::InvalidMetadata(format!(
                    "length input '{length}' not found in model inputs {inputs:?}"
                )));
            }
        }
        if !session
            .outputs()
            .iter()
            .any(|output| output.name() == contract.logits_output)
        {
            return Err(RuntimeError::InvalidMetadata(format!(
                "logits output '{}' not found in model",
                contract.logits_output
            )));
        }

        Ok(Self {
            session,
            contract,
            provider: config.provider,
            session_creation_ms,
            cpu_fallback_allowed: config.tuning.allow_cpu_fallback,
        })
    }

    pub fn provider(&self) -> ProviderKind {
        self.provider
    }

    pub fn session_creation_ms(&self) -> f64 {
        self.session_creation_ms
    }

    pub fn cpu_fallback_allowed(&self) -> bool {
        self.cpu_fallback_allowed
    }

    pub fn run_waveform(&mut self, samples: &[f32]) -> Result<InferenceOutput> {
        if samples.is_empty() {
            return Err(RuntimeError::UnsupportedContract("empty waveform".into()));
        }
        if !samples.iter().all(|value| value.is_finite()) {
            return Err(RuntimeError::NonFiniteTensor("waveform input".into()));
        }

        let waveform = TensorRef::from_array_view(([1usize, samples.len()], samples))?;
        let started = Instant::now();
        let outputs = if let Some(length_name) = self.contract.length_input.as_deref() {
            let length_data = [i64::try_from(samples.len()).map_err(|_| {
                RuntimeError::UnsupportedContract("waveform length does not fit in i64".into())
            })?];
            let length = TensorRef::from_array_view(([1usize], &length_data[..]))?;
            self.session.run(ort::inputs![
                self.contract.primary_input.as_str() => waveform,
                length_name => length,
            ])?
        } else {
            self.session.run(ort::inputs![
                self.contract.primary_input.as_str() => waveform,
            ])?
        };
        let elapsed = started.elapsed().as_secs_f64() * 1000.0;

        let output = &outputs[self.contract.logits_output.as_str()];
        let (shape, data) = output.try_extract_tensor::<f32>()?;
        let shape: Vec<usize> = shape
            .iter()
            .map(|dimension| {
                usize::try_from(*dimension).map_err(|_| {
                    RuntimeError::UnsupportedContract(format!(
                        "negative or oversized logits dimension: {dimension}"
                    ))
                })
            })
            .collect::<Result<Vec<_>>>()?;
        if shape.iter().any(|dimension| *dimension == 0) {
            return Err(RuntimeError::UnsupportedContract(format!(
                "zero-dimension logits shape is not accepted: {shape:?}"
            )));
        }
        if !data.iter().all(|value| value.is_finite()) {
            return Err(RuntimeError::NonFiniteTensor(format!(
                "{} output",
                self.contract.logits_output
            )));
        }
        let token_ids = greedy_ctc_ids(data, &shape, self.contract.blank_id)?;

        Ok(InferenceOutput {
            token_ids,
            inference_ms: elapsed,
        })
    }
}

fn builder_error(error: ort::Error<ort::session::builder::SessionBuilder>) -> RuntimeError {
    RuntimeError::ProviderConfiguration(error.to_string())
}

fn greedy_ctc_ids(logits: &[f32], shape: &[usize], blank_id: i64) -> Result<Vec<i64>> {
    let (time, vocab) = match shape {
        [time, vocab] => (*time, *vocab),
        [1, time, vocab] => (*time, *vocab),
        _ => {
            return Err(RuntimeError::UnsupportedContract(format!(
                "CTC logits must have [T,V] or [1,T,V] shape, got {shape:?}"
            )))
        }
    };
    if vocab == 0 || logits.len() != time.saturating_mul(vocab) {
        return Err(RuntimeError::UnsupportedContract(
            "CTC logits shape/data length mismatch".into(),
        ));
    }

    let mut output = Vec::with_capacity(time.min(256));
    let mut previous = None;
    for frame in logits.chunks_exact(vocab) {
        let (index, _) = frame
            .iter()
            .enumerate()
            .max_by(|left, right| left.1.total_cmp(right.1))
            .ok_or_else(|| RuntimeError::UnsupportedContract("empty CTC frame".into()))?;
        let id = i64::try_from(index).map_err(|_| {
            RuntimeError::UnsupportedContract("CTC token index does not fit in i64".into())
        })?;
        if previous != Some(id) && id != blank_id {
            output.push(id);
        }
        previous = Some(id);
    }
    Ok(output)
}
