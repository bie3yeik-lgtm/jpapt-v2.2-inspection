use crate::{CanonicalAudio, Result};

#[derive(Debug, Clone)]
pub struct FeatureBatch {
    pub values: Vec<f32>,
    pub shape: Vec<usize>,
    pub length: i64,
}

pub trait Frontend: Send + Sync {
    fn extract(&self, audio: &CanonicalAudio) -> Result<FeatureBatch>;
}
