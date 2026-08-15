use std::{path::{Path, PathBuf}, time::Instant};
use ort::{session::Session, value::Tensor};
use crate::{Result, RuntimeError, metadata::model_metadata::{InputKind, RuntimeContract}, providers::{self, ProviderKind}, tensors::LogitsTensor};

#[derive(Debug, Clone)]
pub struct SessionConfig { pub model_path: PathBuf, pub provider: ProviderKind }
impl SessionConfig { pub fn new(model_path: impl AsRef<Path>, provider: ProviderKind)->Self { Self { model_path:model_path.as_ref().to_path_buf(), provider } } }

#[derive(Debug, Clone)]
pub struct InferenceOutput { pub logits: LogitsTensor, pub inference_ms: f64 }

pub struct OrtCtcSession { session: Session, contract: RuntimeContract, provider: ProviderKind }

impl OrtCtcSession {
    pub fn create(config: SessionConfig, contract: RuntimeContract) -> Result<Self> {
        if contract.input_kind != InputKind::CanonicalWaveform { return Err(RuntimeError::UnsupportedContract("Rust runtime currently requires canonical_waveform input; external NeMo features stay in the Python export/reference layer".into())); }
        let builder = Session::builder()?;
        let builder = providers::configure(builder, config.provider)?;
        let session = builder.commit_from_file(&config.model_path)?;
        let names: Vec<&str> = session.inputs().iter().map(|x| x.name()).collect();
        if !names.iter().any(|n| *n == contract.primary_input) { return Err(RuntimeError::InvalidMetadata(format!("primary input '{}' not found in model inputs {names:?}", contract.primary_input))); }
        if let Some(length) = &contract.length_input { if !names.iter().any(|n| *n == length) { return Err(RuntimeError::InvalidMetadata(format!("length input '{length}' not found in model"))); } }
        if !session.outputs().iter().any(|x| x.name() == contract.logits_output) { return Err(RuntimeError::InvalidMetadata(format!("logits output '{}' not found in model", contract.logits_output))); }
        Ok(Self { session, contract, provider: config.provider })
    }

    pub fn provider(&self)->ProviderKind { self.provider }
    pub fn contract(&self)->&RuntimeContract { &self.contract }

    pub fn run_waveform(&mut self, samples: &[f32]) -> Result<InferenceOutput> {
        if samples.is_empty() { return Err(RuntimeError::UnsupportedContract("empty waveform".into())); }
        let waveform = Tensor::from_array(([1usize, samples.len()], samples.to_vec().into_boxed_slice()))?;
        let started = Instant::now();
        let outputs = if self.contract.length_input.is_some() {
            let length = Tensor::from_array(([1usize], vec![samples.len() as i64].into_boxed_slice()))?;
            self.session.run(ort::inputs![waveform, length])?
        } else {
            self.session.run(ort::inputs![waveform])?
        };
        let elapsed = started.elapsed().as_secs_f64() * 1000.0;
        let output = &outputs[self.contract.logits_output.as_str()];
        let (shape, data) = output.try_extract_tensor::<f32>()?;
        let shape = shape.iter().map(|&d| d.max(0) as usize).collect();
        Ok(InferenceOutput { logits: LogitsTensor { shape, values: data.to_vec() }, inference_ms: elapsed })
    }
}
