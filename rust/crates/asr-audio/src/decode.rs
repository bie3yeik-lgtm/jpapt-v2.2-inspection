use std::path::Path;

use crate::error::{AudioError, Result};

#[derive(Debug, Clone)]
pub struct DecodedAudio {
    pub channels: Vec<Vec<f32>>,
    pub sample_rate_hz: u32,
}

impl DecodedAudio {
    pub fn frames(&self) -> usize { self.channels.first().map_or(0, Vec::len) }
}

pub fn decode_wav(path: impl AsRef<Path>) -> Result<DecodedAudio> {
    let path = path.as_ref();
    let mut reader = hound::WavReader::open(path).map_err(|source| AudioError::Decode { path: path.to_path_buf(), source })?;
    let spec = reader.spec();
    if spec.sample_rate == 0 { return Err(AudioError::InvalidSampleRate(0)); }
    let channels = usize::from(spec.channels);
    if channels == 0 { return Err(AudioError::Unsupported("zero-channel WAV".into())); }
    let mut output = vec![Vec::new(); channels];
    match spec.sample_format {
        hound::SampleFormat::Float => {
            for (i, sample) in reader.samples::<f32>().enumerate() {
                let value = sample.map_err(|source| AudioError::Decode { path: path.to_path_buf(), source })?;
                output[i % channels].push(value.clamp(-1.0, 1.0));
            }
        }
        hound::SampleFormat::Int => {
            let bits = u32::from(spec.bits_per_sample);
            if bits == 0 || bits > 32 { return Err(AudioError::Unsupported(format!("{}-bit integer WAV", bits))); }
            let scale = ((1_i64 << (bits - 1)) - 1) as f32;
            for (i, sample) in reader.samples::<i32>().enumerate() {
                let value = sample.map_err(|source| AudioError::Decode { path: path.to_path_buf(), source })? as f32 / scale;
                output[i % channels].push(value.clamp(-1.0, 1.0));
            }
        }
    }
    if output.iter().all(Vec::is_empty) { return Err(AudioError::Empty); }
    Ok(DecodedAudio { channels: output, sample_rate_hz: spec.sample_rate })
}
