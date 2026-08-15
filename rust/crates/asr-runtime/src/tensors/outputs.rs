#[derive(Debug, Clone)]
pub struct LogitsTensor { pub shape: Vec<usize>, pub values: Vec<f32> }
impl LogitsTensor { pub fn rank(&self)->usize { self.shape.len() } pub fn vocabulary_size(&self)->Option<usize>{ self.shape.last().copied() } }
