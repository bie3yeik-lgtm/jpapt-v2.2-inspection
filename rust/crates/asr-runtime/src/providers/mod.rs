mod coreml;
mod cpu;
mod cuda;

use std::{fmt, str::FromStr};

use ort::session::builder::SessionBuilder;

use crate::{Result, RuntimeError};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProviderKind {
    Cpu,
    Cuda,
    CoreMl,
}

impl ProviderKind {
    pub fn ort_name(self) -> &'static str {
        match self {
            Self::Cpu => "CPUExecutionProvider",
            Self::Cuda => "CUDAExecutionProvider",
            Self::CoreMl => "CoreMLExecutionProvider",
        }
    }

    pub fn compiled(self) -> bool {
        match self {
            Self::Cpu => true,
            Self::Cuda => cfg!(feature = "cuda"),
            Self::CoreMl => cfg!(feature = "coreml"),
        }
    }
}

impl fmt::Display for ProviderKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{}",
            match self {
                Self::Cpu => "cpu",
                Self::Cuda => "cuda",
                Self::CoreMl => "coreml",
            }
        )
    }
}

impl FromStr for ProviderKind {
    type Err = RuntimeError;

    fn from_str(value: &str) -> Result<Self> {
        match value.to_ascii_lowercase().as_str() {
            "cpu" => Ok(Self::Cpu),
            "cuda" => Ok(Self::Cuda),
            "coreml" => Ok(Self::CoreMl),
            _ => Err(RuntimeError::UnsupportedContract(format!(
                "unknown provider {value}"
            ))),
        }
    }
}

pub fn configure(builder: SessionBuilder, provider: ProviderKind) -> Result<SessionBuilder> {
    if !provider.compiled() {
        return Err(RuntimeError::ProviderNotCompiled(provider.to_string()));
    }
    match provider {
        ProviderKind::Cpu => cpu::configure(builder),
        ProviderKind::Cuda => cuda::configure(builder),
        ProviderKind::CoreMl => coreml::configure(builder),
    }
}
