use std::path::PathBuf;

#[derive(Debug, thiserror::Error)]
pub enum AudioError {
    #[error("failed to decode WAV {path}: {source}")]
    Decode { path: PathBuf, #[source] source: hound::Error },
    #[error("audio contains no samples")]
    Empty,
    #[error("invalid sample rate: {0}")]
    InvalidSampleRate(u32),
    #[error("unsupported WAV format: {0}")]
    Unsupported(String),
}

pub type Result<T> = std::result::Result<T, AudioError>;
