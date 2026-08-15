use crate::{CanonicalAudio, Result};
use super::{FeatureBatch, Frontend};

#[derive(Debug, Clone, Copy)]
pub struct ParakeetFrontendConfig {
    pub sample_rate_hz: u32,
}

impl Default for ParakeetFrontendConfig {
    fn default() -> Self { Self { sample_rate_hz: 16_000 } }
}

/// Runtime frontend for candidates that embed preprocessing in the ONNX graph.
/// External NeMo mel preprocessing remains an export/reference responsibility.
#[derive(Debug, Default)]
pub struct WaveformFrontend;

impl Frontend for WaveformFrontend {
    fn extract(&self, audio: &CanonicalAudio) -> Result<FeatureBatch> {
        Ok(FeatureBatch { values: audio.waveform.clone(), shape: vec![1, audio.waveform.len()], length: audio.waveform.len() as i64 })
    }
}
