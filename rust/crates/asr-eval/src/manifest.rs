use crate::{
    dataset::ResolvedManifest,
    error::{EvalError, Result},
};
use std::{fs, path::Path};

pub fn load_resolved_manifest(path: impl AsRef<Path>) -> Result<ResolvedManifest> {
    let value: ResolvedManifest = serde_json::from_str(&fs::read_to_string(path.as_ref())?)?;
    value.validate().map_err(EvalError::InvalidInput)?;
    Ok(value)
}
