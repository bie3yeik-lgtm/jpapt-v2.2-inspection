use std::path::PathBuf;

#[derive(Debug, thiserror::Error)]
pub enum ContractError {
    #[error("I/O error for {path}: {source}")]
    Io {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
    #[error("invalid JSON in {path}: {source}")]
    Json {
        path: PathBuf,
        #[source]
        source: serde_json::Error,
    },
    #[error("contract violation: {0}")]
    Validation(String),
}

pub type Result<T> = std::result::Result<T, ContractError>;

impl ContractError {
    pub fn validation(message: impl Into<String>) -> Self {
        Self::Validation(message.into())
    }
}
