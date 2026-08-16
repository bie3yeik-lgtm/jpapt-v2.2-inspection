#[derive(Debug, thiserror::Error)]
pub enum EvalError {
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error(transparent)]
    Audio(#[from] asr_audio::AudioError),
    #[error(transparent)]
    Runtime(#[from] asr_runtime::RuntimeError),
    #[error("invalid evaluation input: {0}")]
    InvalidInput(String),
    #[error("token {0} is missing from vocabulary")]
    UnknownToken(i64),
}
pub type Result<T> = std::result::Result<T, EvalError>;
