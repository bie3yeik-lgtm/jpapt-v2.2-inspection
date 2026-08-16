use std::path::Path;

use crate::{
    dataset::ResolvedManifest,
    error::{EvalError, Result},
};

pub fn load_resolved_manifest(path: impl AsRef<Path>) -> Result<ResolvedManifest> {
    asr_input::load_evaluation_input(path).map_err(|error| EvalError::InvalidInput(error.to_string()))
}
