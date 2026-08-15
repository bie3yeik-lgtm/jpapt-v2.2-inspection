use std::{collections::BTreeMap, fs, path::Path};
use crate::Result;
#[derive(Debug,Clone,Default)] pub struct ExpectedOutputs { pub by_id:BTreeMap<String,serde_json::Value> }
impl ExpectedOutputs { pub fn load(path:impl AsRef<Path>)->Result<Self>{ let value:serde_json::Value=serde_json::from_str(&fs::read_to_string(path)?)?; let mut by_id=BTreeMap::new(); if let Some(samples)=value.get("samples").and_then(|v|v.as_array()){ for sample in samples { if let Some(id)=sample.get("id").and_then(|v|v.as_str()){by_id.insert(id.to_owned(),sample.clone());} } } Ok(Self{by_id}) } }
