mod hf_parquet;
mod json;
mod model;
mod parquet;

use std::path::Path;

use anyhow::{Result, bail};

pub use hf_parquet::{HfAudioParquetSpec, materialize_hf_audio_parquet};
pub use model::{EVALUATION_INPUT_SCHEMA_VERSION, EvaluationInputSet, MaterializedSample};
pub use parquet::{evaluation_input_parquet_schema, load_parquet_input, write_parquet_input};

pub fn load_evaluation_input(path: impl AsRef<Path>) -> Result<EvaluationInputSet> {
    let path = path.as_ref();
    match path.extension().and_then(|value| value.to_str()) {
        Some("json") => json::load_json_input(path),
        Some("parquet") => parquet::load_parquet_input(path),
        extension => bail!(
            "unsupported evaluation input extension {:?}; expected .json or .parquet",
            extension
        ),
    }
}
