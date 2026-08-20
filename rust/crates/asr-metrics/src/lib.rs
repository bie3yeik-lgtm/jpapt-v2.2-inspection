pub mod cer;
pub mod edit_distance;
pub mod error;
pub mod memory;
pub mod parity;
pub mod timing;
pub mod wer;

pub use cer::{character_error_rate, normalize_text};
pub use edit_distance::edit_distance;
pub use memory::current_process_memory_mb;
pub use parity::{TensorComparison, compare_f32};
pub use timing::{
    RtfError, RtfMetrics, TimingDistribution, distribution, estimate_cost_per_audio_hour,
    rtf_metrics,
};
pub use wer::word_error_rate;
