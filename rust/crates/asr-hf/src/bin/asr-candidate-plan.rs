use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::Value;

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-candidate-plan: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let path = args
        .next()
        .map(PathBuf::from)
        .ok_or_else(|| usage().to_owned())?;
    if args.next().is_some() {
        return Err(usage().to_owned());
    }
    let uploads = validate_fresh_upload_plan(&path)?;
    println!("upload_count={uploads}");
    Ok(())
}

fn usage() -> &'static str {
    "usage: asr-candidate-plan <hf-sync-plan.jsonl>"
}

fn validate_fresh_upload_plan(path: &Path) -> Result<usize, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let mut actions = Vec::new();
    for (index, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() {
            continue;
        }
        let value: Value = serde_json::from_str(line)
            .map_err(|error| format!("{} line {}: {error}", path.display(), index + 1))?;
        let object = value.as_object().ok_or_else(|| {
            format!(
                "{} line {}: sync plan entry must be a JSON object",
                path.display(),
                index + 1
            )
        })?;
        let Some(action) = object.get("action") else {
            continue;
        };
        if action.is_null() {
            continue;
        }
        let action = action.as_str().ok_or_else(|| {
            format!(
                "{} line {}: action must be a string when present",
                path.display(),
                index + 1
            )
        })?;
        actions.push(action.to_ascii_lowercase());
    }
    if actions.is_empty() {
        return Err("candidate sync plan contains no file operations".to_owned());
    }
    let mut unsafe_actions = actions
        .iter()
        .filter(|action| action.as_str() != "upload")
        .cloned()
        .collect::<Vec<_>>();
    unsafe_actions.sort();
    unsafe_actions.dedup();
    if !unsafe_actions.is_empty() {
        return Err(format!(
            "candidate prefix is not write-once clean; unexpected sync actions: {}",
            unsafe_actions.join(", ")
        ));
    }
    Ok(actions.len())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_plan(contents: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = env::temp_dir().join(format!("asr-candidate-plan-{nonce}.jsonl"));
        fs::write(&path, contents).unwrap();
        path
    }

    #[test]
    fn accepts_upload_only_plan() {
        let path = temp_plan("{\"action\":\"upload\"}\n{\"action\":\"UPLOAD\"}\n");
        assert_eq!(validate_fresh_upload_plan(&path).unwrap(), 2);
        let _ = fs::remove_file(path);
    }

    #[test]
    fn rejects_non_upload_actions() {
        let path = temp_plan("{\"action\":\"upload\"}\n{\"action\":\"delete\"}\n");
        let error = validate_fresh_upload_plan(&path).unwrap_err();
        assert!(error.contains("delete"));
        let _ = fs::remove_file(path);
    }

    #[test]
    fn rejects_plan_without_operations() {
        let path = temp_plan("{\"path\":\"model.onnx\"}\n");
        assert!(validate_fresh_upload_plan(&path).is_err());
        let _ = fs::remove_file(path);
    }
}
