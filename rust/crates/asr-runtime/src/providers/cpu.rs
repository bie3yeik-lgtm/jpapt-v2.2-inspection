use ort::{ep::ExecutionProvider as _, session::builder::SessionBuilder};
use crate::Result;

pub(super) fn configure(builder: SessionBuilder) -> Result<SessionBuilder> {
    Ok(builder.with_execution_providers([ort::ep::CPU::default().build()])?)
}
