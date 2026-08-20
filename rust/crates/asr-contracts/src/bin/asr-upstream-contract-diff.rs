use serde::Serialize;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const CONTRACT_PREFIXES: &[&str] = &[
    "config/",
    "contracts/",
    "evaluation/schemas/",
    ".github/workflows/",
    "rust/crates/asr-contracts/",
    "docs/",
];

#[derive(Debug, Serialize)]
struct UpstreamContractDiffReport {
    schema_version: u32,
    source_repository: String,
    baseline_revision: String,
    public_revision: String,
    changed_files: Vec<String>,
    contract_changed_files: Vec<String>,
    summary: ReportSummary,
}

#[derive(Debug, Serialize)]
struct ReportSummary {
    total_changed_files: usize,
    contract_changed_files: usize,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-upstream-contract-diff: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(usage)?;
    match command.as_str() {
        "compare" => compare_command(args),
        _ => Err(format!("unsupported command {command:?}\n{}", usage())),
    }
}

fn compare_command(mut args: impl Iterator<Item = String>) -> Result<(), String> {
    let mut repo_root = PathBuf::from(".");
    let mut baseline = None;
    let mut head = None;
    let mut output = None;
    let mut source_repository = "largoyo/Premiere-AutoProcess-Plugin".to_owned();

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--repo-root" => repo_root = PathBuf::from(required_value(&mut args, "--repo-root")?),
            "--baseline" => baseline = Some(required_value(&mut args, "--baseline")?),
            "--head" | "--public-revision" => {
                head = Some(required_value(&mut args, "--head/--public-revision")?)
            }
            "--output" => output = Some(PathBuf::from(required_value(&mut args, "--output")?)),
            "--source-repository" => {
                source_repository = required_value(&mut args, "--source-repository")?
            }
            _ => return Err(format!("unsupported compare argument {arg:?}")),
        }
    }

    let baseline = baseline.ok_or_else(|| "compare requires --baseline".to_owned())?;
    let head = head.ok_or_else(|| "compare requires --head".to_owned())?;
    let output = output.ok_or_else(|| "compare requires --output".to_owned())?;

    validate_sha(&baseline)?;
    validate_sha(&head)?;
    if baseline == head {
        return Err("baseline and head revisions must differ".to_owned());
    }
    validate_source_repository(&source_repository)?;

    let report = build_report(&repo_root, &source_repository, &baseline, &head)?;
    if let Some(parent) = output.parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
    }
    fs::write(
        &output,
        serde_json::to_string_pretty(&report).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())?;
    println!(
        "upstream contract diff: {} contract file(s) changed between {}..{}",
        report.summary.contract_changed_files, baseline, head
    );
    Ok(())
}

fn build_report(
    repo_root: &Path,
    source_repository: &str,
    baseline: &str,
    head: &str,
) -> Result<UpstreamContractDiffReport, String> {
    if baseline == head {
        return Err("baseline and head revisions must differ".to_owned());
    }
    ensure_git_ref(repo_root, baseline)?;
    ensure_git_ref(repo_root, head)?;

    let changed_files = git_diff_names(repo_root, baseline, head)?;
    let contract_changed_files: Vec<String> = changed_files
        .iter()
        .filter(|path| is_contract_path(path))
        .cloned()
        .collect();

    Ok(UpstreamContractDiffReport {
        schema_version: 1,
        source_repository: source_repository.to_owned(),
        baseline_revision: baseline.to_owned(),
        public_revision: head.to_owned(),
        summary: ReportSummary {
            total_changed_files: changed_files.len(),
            contract_changed_files: contract_changed_files.len(),
        },
        contract_changed_files,
        changed_files,
    })
}

fn is_contract_path(path: &str) -> bool {
    CONTRACT_PREFIXES
        .iter()
        .any(|prefix| path.starts_with(prefix))
}

fn validate_sha(sha: &str) -> Result<(), String> {
    if sha.len() != 40 || !sha.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err(format!(
            "revision must be a lowercase 40-hex SHA: {sha}"
        ));
    }
    if sha.chars().any(|c| c.is_ascii_uppercase()) {
        return Err(format!("revision must use lowercase hex: {sha}"));
    }
    Ok(())
}

fn validate_source_repository(value: &str) -> Result<(), String> {
    let parts: Vec<&str> = value.split('/').collect();
    if parts.len() != 2 || parts.iter().any(|part| part.is_empty()) {
        return Err(format!(
            "source repository must use owner/name form: {value}"
        ));
    }
    Ok(())
}

fn ensure_git_ref(repo_root: &Path, revision: &str) -> Result<(), String> {
    let status = Command::new("git")
        .args(["cat-file", "-e", &format!("{revision}^{{commit}}")])
        .current_dir(repo_root)
        .status()
        .map_err(|error| format!("git cat-file failed: {error}"))?;
    if !status.success() {
        return Err(format!("unknown git revision: {revision}"));
    }
    Ok(())
}

fn git_diff_names(repo_root: &Path, baseline: &str, head: &str) -> Result<Vec<String>, String> {
    let range = format!("{baseline}..{head}");
    let output = Command::new("git")
        .args(["diff", "--name-only", &range])
        .current_dir(repo_root)
        .output()
        .map_err(|error| format!("git diff failed: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "git diff --name-only {range} failed with status {}",
            output.status
        ));
    }
    let stdout = String::from_utf8(output.stdout).map_err(|error| error.to_string())?;
    Ok(stdout
        .lines()
        .filter(|line| !line.is_empty())
        .map(str::to_owned)
        .collect())
}

fn required_value(
    args: &mut impl Iterator<Item = String>,
    flag: &str,
) -> Result<String, String> {
    args.next()
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn usage() -> String {
    [
        "usage:",
        "  asr-upstream-contract-diff compare \\",
        "    --repo-root . \\",
        "    --baseline <40-hex-sha> \\",
        "    --head <40-hex-sha> \\",
        "    --output .ci/upstream-contract-diff/report.json \\",
        "    [--source-repository owner/name]",
    ]
    .join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Command;
    use std::{fs, path::Path};

    fn init_repo(root: &Path) {
        assert!(Command::new("git")
            .arg("init")
            .current_dir(root)
            .status()
            .unwrap()
            .success());
        assert!(Command::new("git")
            .args(["config", "user.email", "test@example.com"])
            .current_dir(root)
            .status()
            .unwrap()
            .success());
        assert!(Command::new("git")
            .args(["config", "user.name", "test"])
            .current_dir(root)
            .status()
            .unwrap()
            .success());
    }

    fn commit_all(root: &Path, message: &str) -> String {
        Command::new("git")
            .args(["add", "-A"])
            .current_dir(root)
            .status()
            .unwrap();
        assert!(Command::new("git")
            .args(["commit", "-m", message])
            .current_dir(root)
            .status()
            .unwrap()
            .success());
        String::from_utf8(
            Command::new("git")
                .args(["rev-parse", "HEAD"])
                .current_dir(root)
                .output()
                .unwrap()
                .stdout,
        )
        .unwrap()
        .trim()
        .to_owned()
    }

    #[test]
    fn classifies_contract_paths() {
        assert!(is_contract_path("config/models/foo.toml"));
        assert!(is_contract_path("evaluation/schemas/run-context.schema.json"));
        assert!(!is_contract_path("python/src/foo.py"));
    }

    #[test]
    fn builds_report_for_contract_changes() {
        let root = tempfile::tempdir().unwrap();
        init_repo(root.path());
        fs::create_dir_all(root.path().join("config")).unwrap();
        fs::write(root.path().join("config/a.toml"), "a=1\n").unwrap();
        let baseline = commit_all(root.path(), "baseline");
        fs::write(root.path().join("config/a.toml"), "a=2\n").unwrap();
        fs::write(root.path().join("scratch.txt"), "noise\n").unwrap();
        let head = commit_all(root.path(), "head");

        let report = build_report(
            root.path(),
            "largoyo/Premiere-AutoProcess-Plugin",
            &baseline,
            &head,
        )
        .unwrap();
        assert_eq!(report.summary.total_changed_files, 2);
        assert_eq!(report.summary.contract_changed_files, 1);
        assert_eq!(report.contract_changed_files, vec!["config/a.toml".to_owned()]);
    }

    #[test]
    fn rejects_identical_revisions() {
        let root = tempfile::tempdir().unwrap();
        init_repo(root.path());
        fs::write(root.path().join("README.md"), "hello\n").unwrap();
        let sha = commit_all(root.path(), "only");
        let err = build_report(root.path(), "owner/repo", &sha, &sha).unwrap_err();
        assert!(err.contains("must differ"));
    }
}
