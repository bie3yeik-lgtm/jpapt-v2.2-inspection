pub mod benchmark;
pub mod cli;
pub mod config;
pub mod dataset;
pub mod decoding;
pub mod error;
pub mod evaluator;
pub mod expected;
pub mod manifest;
pub mod writer;

pub use cli::{Cli, Command};
pub use error::{EvalError, Result};
