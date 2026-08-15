use ort::session::builder::SessionBuilder;
use crate::{Result, RuntimeError};

#[cfg(feature="cuda")]
pub(super) fn configure(builder: SessionBuilder) -> Result<SessionBuilder> {
    use ort::ep::ExecutionProvider as _;
    Ok(builder.with_execution_providers([ort::ep::CUDA::default().build()])?)
}
#[cfg(not(feature="cuda"))]
pub(super) fn configure(_builder: SessionBuilder) -> Result<SessionBuilder> { Err(RuntimeError::ProviderNotCompiled("cuda".into())) }
