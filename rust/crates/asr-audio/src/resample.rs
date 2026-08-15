use crate::error::{AudioError, Result};

pub fn resample_linear(input: &[f32], input_rate: u32, output_rate: u32) -> Result<Vec<f32>> {
    if input_rate == 0 { return Err(AudioError::InvalidSampleRate(input_rate)); }
    if output_rate == 0 { return Err(AudioError::InvalidSampleRate(output_rate)); }
    if input.is_empty() { return Err(AudioError::Empty); }
    if input_rate == output_rate { return Ok(input.to_vec()); }
    let output_len = ((input.len() as u128 * output_rate as u128 + input_rate as u128 / 2) / input_rate as u128) as usize;
    let mut output = Vec::with_capacity(output_len.max(1));
    let ratio = input_rate as f64 / output_rate as f64;
    for i in 0..output_len.max(1) {
        let pos = i as f64 * ratio;
        let left = pos.floor() as usize;
        let right = (left + 1).min(input.len() - 1);
        let frac = (pos - left as f64) as f32;
        output.push(input[left.min(input.len() - 1)] * (1.0 - frac) + input[right] * frac);
    }
    Ok(output)
}
