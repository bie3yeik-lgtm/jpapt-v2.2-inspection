use std::{fs, path::Path};
use chrono::Utc; use sha2::{Digest,Sha256};
use asr_runtime::ProviderKind;
use crate::{config::{RevisionHashes,detect_environment,logical_path}, Result};

pub fn sha256_file(path:&Path)->Result<String>{ let mut f=fs::File::open(path)?; let mut h=Sha256::new(); std::io::copy(&mut f,&mut h)?; Ok(format!("{:x}",h.finalize())) }

pub fn build_run_context(model:&Path, model_id:&str, candidate_id:Option<&str>, provider:ProviderKind, evaluation:&str, revisions:&RevisionHashes)->Result<serde_json::Value>{
 let sha=sha256_file(model)?; let size=fs::metadata(model)?.len(); let now=Utc::now(); let run_id=format!("{}-{}-{}-{}-{}",now.format("%Y%m%dT%H%M%SZ"),model_id.replace(['/','_'],"-"),detect_environment(),provider,&sha[..8]);
 Ok(serde_json::json!({"schema_version":1,"run_id":run_id,"created_at":now.to_rfc3339(),"config_identity":format!("{model_id}:{}:{provider}:{evaluation}",detect_environment()),"model_id":model_id,"environment_id":detect_environment(),"provider_id":provider.to_string(),"evaluation_id":evaluation,"artifact":{"path":logical_path(model),"sha256":sha,"size_bytes":size,"candidate_id":candidate_id,"artifact_role":"primary"},"git":{"repository":std::env::var("GITHUB_REPOSITORY").ok(),"commit":std::env::var("GITHUB_SHA").ok(),"ref":std::env::var("GITHUB_REF").ok(),"dirty":null},"host":{"os":std::env::consts::OS,"architecture":std::env::consts::ARCH,"hostname":null,"python_version":"n/a","implementation":"rust","is_wsl":false,"github_runner_os":std::env::var("RUNNER_OS").ok(),"github_runner_arch":std::env::var("RUNNER_ARCH").ok(),"github_run_id":std::env::var("GITHUB_RUN_ID").ok(),"github_run_attempt":std::env::var("GITHUB_RUN_ATTEMPT").ok()},"runtime":{"implementation":"rust","backend":"onnxruntime","backend_version":null,"provider_id":provider.to_string(),"provider_ort_name":provider.ort_name(),"provider_available":true},"revisions":{"bundle_sha256":revisions.bundle,"reference":{"document_sha256":revisions.reference},"evaluation_schema":{"document_sha256":revisions.evaluation_schema},"datasets":{"document_sha256":revisions.datasets_lock}},"config":{},"metadata":{}}))
}
