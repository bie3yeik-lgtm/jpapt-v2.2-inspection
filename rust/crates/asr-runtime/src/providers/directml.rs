use ort::session::builder::SessionBuilder;

use crate::{Result, RuntimeError};

#[cfg(feature = "directml")]
pub(super) fn configure(builder: SessionBuilder) -> Result<SessionBuilder> {
    builder
        .with_execution_providers([ort::ep::DirectML::default().build()])
        .map_err(|error| RuntimeError::ProviderConfiguration(error.to_string()))
}

#[cfg(not(feature = "directml"))]
pub(super) fn configure(_builder: SessionBuilder) -> Result<SessionBuilder> {
    Err(RuntimeError::ProviderNotCompiled("directml".into()))
}
