pub mod error;
pub mod metadata;
pub mod providers;
pub mod session;

pub use error::{Result, RuntimeError};
pub use metadata::model_metadata::{
    CtcRuntimeContract, DecoderKind, GeneratedArtifact, GeneratedCandidateContract,
    GeneratedRuntimeContract, GeneratedTokenizer, InputKind,
};
pub use providers::ProviderKind;
pub use session::{InferenceOutput, OrtCtcSession, SessionConfig, SessionTuning};

/// Returns the build information reported by the ONNX Runtime library linked
/// through `ort`, including the runtime version, source revision, and compile
/// flags. Persist this value as execution evidence rather than inferring the
/// backend version from Cargo metadata.
pub fn ort_build_info() -> &'static str {
    ort::info()
}
