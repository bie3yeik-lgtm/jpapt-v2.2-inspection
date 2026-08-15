#[derive(Debug, Clone)]
pub struct WaveformInput { pub samples: Vec<f32>, pub length: i64 }
impl WaveformInput { pub fn new(samples: Vec<f32>) -> Self { let length=samples.len() as i64; Self { samples, length } } }
