use ort::session::builder::SessionBuilder;
use crate::{Result, RuntimeError};

#[cfg(feature="directml")]
pub(super) fn configure(builder: SessionBuilder) -> Result<SessionBuilder> {
    use ort::ep::ExecutionProvider as _;
    Ok(builder.with_execution_providers([ort::ep::DirectML::default().build()])?)
}
#[cfg(not(feature="directml"))]
pub(super) fn configure(_builder: SessionBuilder) -> Result<SessionBuilder> { Err(RuntimeError::ProviderNotCompiled("directml".into())) }
