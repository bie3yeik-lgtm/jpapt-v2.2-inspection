use std::{fs, path::{Path,PathBuf}};
use sha2::{Digest,Sha256};
use crate::Result;

#[derive(Debug,Clone)]
pub struct RevisionBundleData {
 pub reference_hash:String,
 pub evaluation_schema_hash:String,
 pub datasets_lock_hash:String,
 pub bundle_hash:String,
 pub config_version:Option<String>,
 pub reference:serde_json::Value,
 pub evaluation_schema:serde_json::Value,
 pub datasets_lock:serde_json::Value,
}

fn canonical(path:&Path)->Result<(serde_json::Value,String)>{
 let value:serde_json::Value=serde_json::from_str(&fs::read_to_string(path)?)?;
 let bytes=serde_json::to_vec(&value)?;
 Ok((value,format!("{:x}",Sha256::digest(bytes))))
}

pub fn load_revision_bundle(root:impl AsRef<Path>)->Result<RevisionBundleData>{
 let root=root.as_ref();
 let (reference,reference_hash)=canonical(&root.join("reference.json"))?;
 let (evaluation_schema,evaluation_schema_hash)=canonical(&root.join("evaluation-schema.json"))?;
 let (datasets_lock,datasets_lock_hash)=canonical(&root.join("datasets-lock.json"))?;
 let mut h=Sha256::new();
 h.update(reference_hash.as_bytes());
 h.update(evaluation_schema_hash.as_bytes());
 h.update(datasets_lock_hash.as_bytes());
 let bundle_hash=format!("{:x}",h.finalize());
 let resolved=root.parent().unwrap_or(root).join("resolved.json");
 let config_version=if resolved.is_file(){
   let v:serde_json::Value=serde_json::from_str(&fs::read_to_string(resolved)?)?;
   v.get("config_version").and_then(|x|x.as_str()).map(ToOwned::to_owned)
 }else{None};
 Ok(RevisionBundleData{reference_hash,evaluation_schema_hash,datasets_lock_hash,bundle_hash,config_version,reference,evaluation_schema,datasets_lock})
}

pub fn detect_environment()->&'static str { if cfg!(target_os="windows") {"windows"} else if cfg!(target_os="macos") {"macos"} else {"linux"} }
pub fn logical_path(path:&Path)->String { path.to_string_lossy().replace('\\',"/") }
pub fn require_file(path:impl AsRef<Path>)->Result<PathBuf>{ let p=path.as_ref().to_path_buf(); if !p.is_file(){return Err(crate::EvalError::InvalidInput(format!("file does not exist: {}",p.display())));} Ok(p) }
