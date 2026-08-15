use std::{collections::BTreeMap, fs, path::Path};
use crate::{EvalError, Result};

#[derive(Debug, Clone)]
pub struct Vocabulary { id_to_token: BTreeMap<i64, String> }
impl Vocabulary {
    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        let value: serde_json::Value = serde_json::from_str(&fs::read_to_string(path)?)?;
        let mut map=BTreeMap::new();
        match value {
            serde_json::Value::Array(items) => for (i,v) in items.into_iter().enumerate(){ map.insert(i as i64, v.as_str().map(str::to_owned).unwrap_or_else(|| v.to_string())); },
            serde_json::Value::Object(items) => for (k,v) in items { let id=k.parse::<i64>().map_err(|_| EvalError::InvalidInput(format!("invalid vocabulary id {k}")))?; map.insert(id, v.as_str().map(str::to_owned).unwrap_or_else(|| v.to_string())); },
            _ => return Err(EvalError::InvalidInput("vocabulary JSON must be a list or object".into())),
        }
        Ok(Self{id_to_token:map})
    }
    pub fn decode(&self, ids:&[i64])->Result<String>{ let mut out=String::new(); for id in ids { out.push_str(self.id_to_token.get(id).ok_or(EvalError::UnknownToken(*id))?); } Ok(out) }
}

pub fn greedy_ctc_ids(logits:&[f32], shape:&[usize], blank_id:i64)->Result<Vec<i64>> {
    let (time,vocab)=match shape { [t,v] => (*t,*v), [1,t,v] => (*t,*v), _ => return Err(EvalError::InvalidInput(format!("CTC logits must have [T,V] or [1,T,V] shape, got {shape:?}"))) };
    if vocab==0 || logits.len()!=time*vocab { return Err(EvalError::InvalidInput("logits shape/data length mismatch".into())); }
    let mut raw=Vec::with_capacity(time);
    for frame in logits.chunks_exact(vocab) { let (idx,_) = frame.iter().enumerate().max_by(|a,b| a.1.total_cmp(b.1)).unwrap(); raw.push(idx as i64); }
    let mut out=Vec::new(); let mut previous=None;
    for id in raw { if previous != Some(id) && id != blank_id { out.push(id); } previous=Some(id); }
    Ok(out)
}
