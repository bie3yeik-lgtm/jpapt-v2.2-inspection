use ort::session::builder::SessionBuilder;

use crate::{Result, RuntimeError};

pub(super) fn configure(builder: SessionBuilder) -> Result<SessionBuilder> {
    builder
        .with_execution_providers([ort::ep::CPU::default().build()])
        .map_err(|error| RuntimeError::ProviderConfiguration(error.to_string()))
}
