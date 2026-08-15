mod coreml;
mod cpu;
mod cuda;
mod directml;

use std::{fmt, str::FromStr};
use ort::session::builder::SessionBuilder;
use crate::{Result, RuntimeError};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProviderKind { Cpu, Cuda, DirectMl, CoreMl }

impl ProviderKind { pub fn ort_name(self) -> &'static str { match self { Self::Cpu=>"CPUExecutionProvider", Self::Cuda=>"CUDAExecutionProvider", Self::DirectMl=>"DmlExecutionProvider", Self::CoreMl=>"CoreMLExecutionProvider" } } }
impl fmt::Display for ProviderKind { fn fmt(&self, f:&mut fmt::Formatter<'_>)->fmt::Result { write!(f,"{}", match self { Self::Cpu=>"cpu",Self::Cuda=>"cuda",Self::DirectMl=>"directml",Self::CoreMl=>"coreml"}) } }
impl FromStr for ProviderKind { type Err=RuntimeError; fn from_str(s:&str)->Result<Self> { match s.to_ascii_lowercase().as_str(){"cpu"=>Ok(Self::Cpu),"cuda"=>Ok(Self::Cuda),"directml"=>Ok(Self::DirectMl),"coreml"=>Ok(Self::CoreMl),_=>Err(RuntimeError::UnsupportedContract(format!("unknown provider {s}"))) } } }

pub fn configure(builder: SessionBuilder, provider: ProviderKind) -> Result<SessionBuilder> {
    match provider {
        ProviderKind::Cpu => cpu::configure(builder),
        ProviderKind::Cuda => cuda::configure(builder),
        ProviderKind::DirectMl => directml::configure(builder),
        ProviderKind::CoreMl => coreml::configure(builder),
    }
}
