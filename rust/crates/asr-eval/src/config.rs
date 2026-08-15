use std::{fs, path::{Path,PathBuf}};
use sha2::{Digest,Sha256};
use crate::Result;

#[derive(Debug,Clone)]
pub struct RevisionHashes { pub reference:String, pub evaluation_schema:String, pub datasets_lock:String, pub bundle:String }
fn canonical_hash(path:&Path)->Result<String>{ let value:serde_json::Value=serde_json::from_str(&fs::read_to_string(path)?)?; let bytes=serde_json::to_vec(&value)?; Ok(format!("{:x}",Sha256::digest(bytes))) }
pub fn load_revision_hashes(root:impl AsRef<Path>)->Result<RevisionHashes>{ let root=root.as_ref(); let reference=canonical_hash(&root.join("reference.json"))?; let evaluation_schema=canonical_hash(&root.join("evaluation-schema.json"))?; let datasets_lock=canonical_hash(&root.join("datasets-lock.json"))?; let mut h=Sha256::new(); h.update(reference.as_bytes());h.update(evaluation_schema.as_bytes());h.update(datasets_lock.as_bytes()); let bundle=format!("{:x}",h.finalize()); Ok(RevisionHashes{reference,evaluation_schema,datasets_lock,bundle}) }
pub fn detect_environment()->&'static str { if cfg!(target_os="windows") {"windows"} else if cfg!(target_os="macos") {"macos"} else {"linux"} }
pub fn logical_path(path:&Path)->String { path.to_string_lossy().replace('\\',"/") }
pub fn require_file(path:impl AsRef<Path>)->Result<PathBuf>{ let p=path.as_ref().to_path_buf(); if !p.is_file(){return Err(crate::EvalError::InvalidInput(format!("file does not exist: {}",p.display())));} Ok(p) }
