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

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RtfMetrics {
    pub rtf: f64,
    pub rtfx: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RtfError {
    NonFiniteAudioDuration,
    NonFiniteProcessingDuration,
    NonPositiveAudioDuration,
    NegativeProcessingDuration,
    ZeroProcessingDuration,
    NonFiniteGpuPrice,
    NegativeGpuPrice,
}

pub fn rtf_metrics(
    audio_duration_sec: f64,
    processing_duration_sec: f64,
) -> Result<RtfMetrics, RtfError> {
    if !audio_duration_sec.is_finite() {
        return Err(RtfError::NonFiniteAudioDuration);
    }
    if !processing_duration_sec.is_finite() {
        return Err(RtfError::NonFiniteProcessingDuration);
    }
    if audio_duration_sec <= 0.0 {
        return Err(RtfError::NonPositiveAudioDuration);
    }
    if processing_duration_sec < 0.0 {
        return Err(RtfError::NegativeProcessingDuration);
    }
    if processing_duration_sec == 0.0 {
        return Err(RtfError::ZeroProcessingDuration);
    }
    let rtf = processing_duration_sec / audio_duration_sec;
    Ok(RtfMetrics {
        rtf,
        rtfx: 1.0 / rtf,
    })
}

pub fn estimate_cost_per_audio_hour(rtf: f64, gpu_price_per_hour: f64) -> Result<f64, RtfError> {
    if !gpu_price_per_hour.is_finite() {
        return Err(RtfError::NonFiniteGpuPrice);
    }
    if gpu_price_per_hour < 0.0 {
        return Err(RtfError::NegativeGpuPrice);
    }
    if !rtf.is_finite() || rtf <= 0.0 {
        return Err(RtfError::NonPositiveAudioDuration);
    }
    Ok(gpu_price_per_hour * rtf)
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

#[cfg(test)]
mod tests {
    use super::{RtfError, estimate_cost_per_audio_hour, rtf_metrics};

    #[test]
    fn calculates_corpus_rtf_and_rtfx() {
        let metrics = rtf_metrics(3600.0, 180.0).unwrap();
        assert_eq!(metrics.rtf, 0.05);
        assert_eq!(metrics.rtfx, 20.0);
    }

    #[test]
    fn rejects_invalid_measurements() {
        assert_eq!(
            rtf_metrics(0.0, 1.0),
            Err(RtfError::NonPositiveAudioDuration)
        );
        assert_eq!(
            rtf_metrics(f64::NAN, 1.0),
            Err(RtfError::NonFiniteAudioDuration)
        );
        assert_eq!(
            rtf_metrics(1.0, f64::INFINITY),
            Err(RtfError::NonFiniteProcessingDuration)
        );
        assert_eq!(
            rtf_metrics(1.0, -1.0),
            Err(RtfError::NegativeProcessingDuration)
        );
        assert_eq!(rtf_metrics(1.0, 0.0), Err(RtfError::ZeroProcessingDuration));
    }

    #[test]
    fn estimates_cost_from_gpu_hour_price() {
        assert_eq!(estimate_cost_per_audio_hour(0.05, 0.49).unwrap(), 0.0245);
        assert_eq!(
            estimate_cost_per_audio_hour(0.05, -1.0),
            Err(RtfError::NegativeGpuPrice)
        );
        assert_eq!(
            estimate_cost_per_audio_hour(0.05, f64::NAN),
            Err(RtfError::NonFiniteGpuPrice)
        );
    }
}
