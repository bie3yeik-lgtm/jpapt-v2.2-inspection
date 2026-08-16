#[derive(Debug, Clone, Copy, Default)]
pub struct TimingDistribution {
    pub mean_ms: Option<f64>,
    pub median_ms: Option<f64>,
    pub p50_ms: Option<f64>,
    pub p95_ms: Option<f64>,
    pub p99_ms: Option<f64>,
    pub min_ms: Option<f64>,
    pub max_ms: Option<f64>,
}

fn percentile(sorted: &[f64], q: f64) -> f64 {
    let pos = q * (sorted.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = pos.ceil() as usize;
    if lo == hi {
        sorted[lo]
    } else {
        sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo as f64)
    }
}
pub fn distribution(values: &[f64]) -> TimingDistribution {
    if values.is_empty() {
        return TimingDistribution::default();
    }
    let mut v = values.to_vec();
    v.sort_by(f64::total_cmp);
    let mean = v.iter().sum::<f64>() / v.len() as f64;
    TimingDistribution {
        mean_ms: Some(mean),
        median_ms: Some(percentile(&v, 0.5)),
        p50_ms: Some(percentile(&v, 0.5)),
        p95_ms: Some(percentile(&v, 0.95)),
        p99_ms: Some(percentile(&v, 0.99)),
        min_ms: v.first().copied(),
        max_ms: v.last().copied(),
    }
}
