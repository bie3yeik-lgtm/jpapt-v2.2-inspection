use crate::{DecodedAudio, error::{AudioError, Result}, resample_linear};

pub const TARGET_SAMPLE_RATE_HZ: u32 = 16_000;

#[derive(Debug, Clone)]
pub struct CanonicalAudio {
    pub waveform: Vec<f32>,
    pub sample_rate_hz: u32,
}

impl CanonicalAudio {
    pub fn from_decoded(decoded: DecodedAudio) -> Result<Self> {
        if decoded.channels.is_empty() { return Err(AudioError::Empty); }
        let frames = decoded.frames();
        if frames == 0 { return Err(AudioError::Empty); }
        let mut mono = vec![0.0_f32; frames];
        for channel in &decoded.channels {
            for (dst, src) in mono.iter_mut().zip(channel.iter().copied()) { *dst += src; }
        }
        let divisor = decoded.channels.len() as f32;
        for sample in &mut mono { *sample = (*sample / divisor).clamp(-1.0, 1.0); }
        let waveform = resample_linear(&mono, decoded.sample_rate_hz, TARGET_SAMPLE_RATE_HZ)?;
        Ok(Self { waveform, sample_rate_hz: TARGET_SAMPLE_RATE_HZ })
    }
    pub fn duration_sec(&self) -> f64 { self.waveform.len() as f64 / self.sample_rate_hz as f64 }
}
