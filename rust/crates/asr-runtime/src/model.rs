use std::path::{Path, PathBuf};
use crate::{Result, RuntimeError, metadata::model_metadata::CandidateMetadata};

#[derive(Debug, Clone)]
pub struct CandidateModel { pub model_path: PathBuf, pub candidate_dir: PathBuf, pub metadata: CandidateMetadata }

impl CandidateModel {
    pub fn load(model_path: impl AsRef<Path>, candidate_dir: impl AsRef<Path>) -> Result<Self> {
        let model_path = model_path.as_ref().to_path_buf();
        if !model_path.is_file() { return Err(RuntimeError::ModelMissing(model_path)); }
        let candidate_dir = candidate_dir.as_ref().to_path_buf();
        let metadata = CandidateMetadata::load(&candidate_dir)?;
        Ok(Self { model_path, candidate_dir, metadata })
    }
}
