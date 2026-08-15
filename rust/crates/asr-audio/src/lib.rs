pub mod canonical;
pub mod decode;
pub mod error;
pub mod features;
pub mod resample;

pub use canonical::{CanonicalAudio, TARGET_SAMPLE_RATE_HZ};
pub use decode::{DecodedAudio, decode_wav};
pub use error::{AudioError, Result};
pub use resample::resample_linear;
