#[derive(Debug, thiserror::Error)]
pub enum MetricsError {
    #[error("tensor lengths differ: reference={reference}, actual={actual}")]
    ShapeMismatch { reference: usize, actual: usize },
}
