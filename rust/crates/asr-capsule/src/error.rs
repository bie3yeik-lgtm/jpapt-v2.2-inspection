use thiserror::Error;

#[derive(Debug, Error)]
pub enum CapsuleError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("Arrow error: {0}")]
    Arrow(#[from] arrow_schema::ArrowError),

    #[error("Parquet error: {0}")]
    Parquet(#[from] parquet::errors::ParquetError),

    #[error("capsule contract violation: {0}")]
    Contract(String),
}

pub type Result<T> = std::result::Result<T, CapsuleError>;
