use std::f64::consts::PI;

use crate::error::{AudioError, Result};

const TAPS: usize = 16;
const PHASES: usize = 1024;
const CUTOFF_MARGIN: f64 = 0.94;

pub fn resample_bandlimited(input: &[f32], input_rate: u32, output_rate: u32) -> Result<Vec<f32>> {
    if input_rate == 0 {
        return Err(AudioError::InvalidSampleRate(input_rate));
    }
    if output_rate == 0 {
        return Err(AudioError::InvalidSampleRate(output_rate));
    }
    if input.is_empty() {
        return Err(AudioError::Empty);
    }
    if input_rate == output_rate {
        return Ok(input.to_vec());
    }

    let output_len =
        (input.len() as u128 * output_rate as u128).div_ceil(input_rate as u128) as usize;
    let cutoff = (output_rate as f64 / input_rate as f64).min(1.0) * CUTOFF_MARGIN;
    let kernels = build_polyphase_kernels(cutoff);
    let source_per_output = input_rate as f64 / output_rate as f64;
    let mut output = Vec::with_capacity(output_len);

    for output_index in 0..output_len {
        let source_position = output_index as f64 * source_per_output;
        let center = source_position.floor() as isize;
        let fraction = source_position - center as f64;
        let phase = ((fraction * PHASES as f64).round() as usize).min(PHASES - 1);
        let kernel = &kernels[phase];

        let mut value = 0.0_f32;
        for (tap, coefficient) in kernel.iter().enumerate() {
            let offset = tap as isize - (TAPS as isize / 2) + 1;
            let source_index = (center + offset).clamp(0, input.len() as isize - 1) as usize;
            value = coefficient.mul_add(input[source_index], value);
        }
        output.push(value);
    }

    Ok(output)
}

fn build_polyphase_kernels(cutoff: f64) -> Vec<[f32; TAPS]> {
    let mut kernels = Vec::with_capacity(PHASES);
    for phase in 0..PHASES {
        let fraction = phase as f64 / PHASES as f64;
        let mut kernel = [0.0_f32; TAPS];
        let mut sum = 0.0_f64;
        for (tap, coefficient) in kernel.iter_mut().enumerate() {
            let offset = tap as isize - (TAPS as isize / 2) + 1;
            let x = offset as f64 - fraction;
            let sinc = if x.abs() < 1.0e-12 {
                cutoff
            } else {
                (PI * cutoff * x).sin() / (PI * x)
            };
            let position = tap as f64 / (TAPS - 1) as f64;
            let window =
                0.42 - 0.5 * (2.0 * PI * position).cos() + 0.08 * (4.0 * PI * position).cos();
            let value = sinc * window;
            *coefficient = value as f32;
            sum += value;
        }
        if sum.abs() > f64::EPSILON {
            for coefficient in &mut kernel {
                *coefficient = (*coefficient as f64 / sum) as f32;
            }
        }
        kernels.push(kernel);
    }
    kernels
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identity_rate_preserves_samples() {
        let input = [0.0_f32, 0.25, -0.5, 1.0];
        assert_eq!(resample_bandlimited(&input, 16_000, 16_000).unwrap(), input);
    }

    #[test]
    fn output_length_matches_polyphase_ceil_rule() {
        let input = vec![0.0_f32; 10];
        let output = resample_bandlimited(&input, 44_100, 16_000).unwrap();
        let expected = (10_u128 * 16_000_u128).div_ceil(44_100);
        assert_eq!(output.len(), expected as usize);
    }

    #[test]
    fn constant_signal_remains_near_constant() {
        let input = vec![0.5_f32; 4_800];
        let output = resample_bandlimited(&input, 48_000, 16_000).unwrap();
        let mean = output.iter().copied().sum::<f32>() / output.len() as f32;
        assert!((mean - 0.5).abs() < 1.0e-3, "mean={mean}");
    }

    #[test]
    fn downsampling_attenuates_above_target_nyquist() {
        let input: Vec<f32> = (0..4_800)
            .map(|index| if index % 2 == 0 { 1.0 } else { -1.0 })
            .collect();
        let output = resample_bandlimited(&input, 48_000, 16_000).unwrap();
        let rms = (output
            .iter()
            .map(|sample| f64::from(*sample) * f64::from(*sample))
            .sum::<f64>()
            / output.len() as f64)
            .sqrt();
        assert!(rms < 0.1, "aliased high-frequency RMS={rms}");
    }
}
