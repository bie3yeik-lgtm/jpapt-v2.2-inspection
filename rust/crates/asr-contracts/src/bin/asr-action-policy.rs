use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const REQUIRED: &[(&str, &str, bool)] = &[
    ("actions/checkout", "v7", true),
    ("actions/setup-python", "v7", true),
    ("actions/upload-artifact", "v7", true),
    ("actions/cache", "v6", true),
    ("actions/cache/restore", "v6", false),
    ("actions/cache/save", "v6", false),
];

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-action-policy: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let repository_root = match args.next() {
        None => PathBuf::from("."),
        Some(option) if option == "--repository-root" => PathBuf::from(
            args.next()
                .filter(|value| !value.is_empty())
                .ok_or_else(|| "--repository-root requires a value".to_owned())?,
        ),
        Some(other) => return Err(format!("unsupported argument {other:?}")),
    };
    if let Some(extra) = args.next() {
        return Err(format!("unexpected argument {extra:?}"));
    }
    validate_action_versions(&repository_root)
}

fn validate_action_versions(repository_root: &Path) -> Result<(), String> {
    let workflow_root = repository_root.join(".github/workflows");
    let mut paths = fs::read_dir(&workflow_root)
        .map_err(|error| format!("{}: {error}", workflow_root.display()))?
        .filter_map(|entry| entry.ok().map(|entry| entry.path()))
        .filter(|path| path.extension().and_then(|value| value.to_str()) == Some("yml"))
        .collect::<Vec<_>>();
    paths.sort();

    let policy = REQUIRED
        .iter()
        .map(|(action, version, required)| (*action, (*version, *required)))
        .collect::<BTreeMap<_, _>>();
    let mut seen = REQUIRED
        .iter()
        .map(|(action, _, _)| (*action, 0_usize))
        .collect::<BTreeMap<_, _>>();
    let mut errors = Vec::new();

    for path in paths {
        let text = fs::read_to_string(&path)
            .map_err(|error| format!("{}: {error}", path.display()))?;
        for (index, line) in text.lines().enumerate() {
            let Some((action, version)) = parse_uses(line) else {
                continue;
            };
            let Some((expected, _)) = policy.get(action.as_str()) else {
                continue;
            };
            *seen.get_mut(action.as_str()).expect("policy keys are preseeded") += 1;
            if version != *expected {
                let relative = path
                    .strip_prefix(repository_root)
                    .unwrap_or(&path)
                    .display();
                errors.push(format!(
                    "{relative}:{}: {action}@{version} is forbidden; required={action}@{expected}",
                    index + 1
                ));
            }
        }
    }

    let missing = REQUIRED
        .iter()
        .filter(|(action, _, required)| *required && seen[action] == 0)
        .map(|(action, _, _)| *action)
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        errors.push(format!(
            "required version-policy actions were not found in any workflow; if an action is intentionally removed, update the policy explicitly: {missing:?}"
        ));
    }

    if !errors.is_empty() {
        for error in &errors {
            eprintln!("ERROR: {error}");
        }
        return Err(format!("GitHub Actions version policy failed with {} error(s)", errors.len()));
    }

    for (action, version, required) in REQUIRED {
        let requirement = if *required { "required" } else { "if-used" };
        println!(
            "OK: {action}@{version} ({} use(s), {requirement})",
            seen[action]
        );
    }
    Ok(())
}

fn parse_uses(line: &str) -> Option<(String, String)> {
    let marker = "uses:";
    let position = line.find(marker)?;
    if position > 0 {
        let previous = line.as_bytes()[position - 1];
        if previous.is_ascii_alphanumeric() || previous == b'_' {
            return None;
        }
    }
    let tail = line[position + marker.len()..].trim_start();
    if tail.is_empty() || tail.starts_with('#') {
        return None;
    }
    let token = tail.split_whitespace().next()?.split('#').next()?.trim();
    let (action, version) = token.rsplit_once('@')?;
    if action.is_empty() || version.is_empty() {
        return None;
    }
    Some((action.to_owned(), version.to_owned()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_action_reference() {
        assert_eq!(
            parse_uses("      - uses: actions/checkout@v7 # pinned"),
            Some(("actions/checkout".to_owned(), "v7".to_owned()))
        );
    }

    #[test]
    fn ignores_non_uses_text() {
        assert_eq!(parse_uses("reuses: actions/checkout@v6"), None);
    }
}
