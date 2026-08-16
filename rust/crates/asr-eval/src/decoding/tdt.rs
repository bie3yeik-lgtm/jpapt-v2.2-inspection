#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TdtStep {
    pub token_id: i64,
    pub duration: usize,
}

/// Deterministically converts already-decoded TDT token/duration steps to token IDs.
/// Predictor/joint-network search is model-specific and belongs in a future TDT runtime graph adapter.
pub fn tokens_from_steps(steps: &[TdtStep], blank_id: i64) -> Vec<i64> {
    steps
        .iter()
        .filter(|s| s.token_id != blank_id && s.duration > 0)
        .map(|s| s.token_id)
        .collect()
}
