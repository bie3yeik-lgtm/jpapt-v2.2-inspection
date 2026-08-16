use crate::error::MetricsError;

#[derive(Debug, Clone, Copy, Default)]
pub struct TensorComparison {
    pub max_abs_error: f64,
    pub mean_abs_error: f64,
    pub relative_l2: f64,
}

pub fn compare_f32(reference: &[f32], actual: &[f32]) -> Result<TensorComparison, MetricsError> {
    if reference.len() != actual.len() {
        return Err(MetricsError::ShapeMismatch {
            reference: reference.len(),
            actual: actual.len(),
        });
    }
    if reference.is_empty() {
        return Ok(TensorComparison::default());
    }
    let mut max_abs = 0.0_f64;
    let mut sum_abs = 0.0_f64;
    let mut diff_sq = 0.0_f64;
    let mut ref_sq = 0.0_f64;
    for (&r, &a) in reference.iter().zip(actual) {
        let d = (r as f64 - a as f64).abs();
        max_abs = max_abs.max(d);
        sum_abs += d;
        diff_sq += d * d;
        ref_sq += (r as f64) * (r as f64);
    }
    Ok(TensorComparison {
        max_abs_error: max_abs,
        mean_abs_error: sum_abs / reference.len() as f64,
        relative_l2: diff_sq.sqrt() / ref_sq.sqrt().max(f64::EPSILON),
    })
}
