use std::path::PathBuf;

#[derive(Debug, thiserror::Error)]
pub enum RuntimeError {
    #[error("candidate metadata is missing: {0}")]
    MetadataMissing(PathBuf),
    #[error("invalid candidate metadata: {0}")]
    InvalidMetadata(String),
    #[error("model file is missing: {0}")]
    ModelMissing(PathBuf),
    #[error("provider {0} is not compiled into this binary")]
    ProviderNotCompiled(String),
    #[error("failed to configure execution provider: {0}")]
    ProviderConfiguration(String),
    #[error("unsupported runtime contract: {0}")]
    UnsupportedContract(String),
    #[error("ONNX Runtime error: {0}")]
    Ort(#[from] ort::Error),
}

pub type Result<T> = std::result::Result<T, RuntimeError>;
