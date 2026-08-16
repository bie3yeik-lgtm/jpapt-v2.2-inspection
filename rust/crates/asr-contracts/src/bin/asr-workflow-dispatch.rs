use serde::Serialize;
use serde_json::{Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Default, Serialize)]
struct InputSpec {
    required: bool,
    #[serde(rename = "type")]
    kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    default: Option<Value>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    options: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
struct WorkflowSpec {
    file: String,
    alias: String,
    name: String,
    workflow_dispatch: bool,
    inputs: BTreeMap<String, InputSpec>,
}

#[derive(Debug, Serialize)]
struct ResolvedDispatch {
    workflow: String,
    alias: String,
    name: String,
    r#ref: String,
    inputs: Map<String, Value>,
    body: Value,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-workflow-dispatch: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(usage)?;
    let root = repository_root()?;
    let workflows = load_workflows(&root)?;

    match command.as_str() {
        "list" => {
            reject_extra(args)?;
            for workflow in workflows.values() {
                if workflow.file == "repository-dispatch.yml" {
                    continue;
                }
                println!(
                    "{}\t{}\t{}\t{}",
                    workflow.alias,
                    workflow.file,
                    workflow.name,
                    workflow.inputs.len()
                );
            }
        }
        "describe" => {
            let selector = args.next().ok_or_else(|| "describe requires <workflow>".to_owned())?;
            reject_extra(args)?;
            let workflow = select_workflow(&workflows, &selector)?;
            println!(
                "{}",
                serde_json::to_string_pretty(workflow).map_err(|error| error.to_string())?
            );
        }
        "validate" => {
            reject_extra(args)?;
            validate_catalog(&workflows)?;
            println!("OK: {} workflow(s) are repository-dispatch reachable", workflows.len() - 1);
        }
        "resolve" => resolve_command(args, &workflows)?,
        _ => return Err(format!("unsupported command {command:?}\n{}", usage())),
    }
    Ok(())
}

fn resolve_command(
    mut args: impl Iterator<Item = String>,
    workflows: &BTreeMap<String, WorkflowSpec>,
) -> Result<(), String> {
    let mut selector = None;
    let mut target_ref = "main".to_owned();
    let mut inputs_json = "{}".to_owned();
    let mut github_output = None::<PathBuf>;

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--workflow" => selector = Some(required_value(&mut args, "--workflow")?),
            "--ref" => target_ref = required_value(&mut args, "--ref")?,
            "--inputs-json" => inputs_json = required_value(&mut args, "--inputs-json")?,
            "--github-output" => {
                github_output = Some(PathBuf::from(required_value(&mut args, "--github-output")?))
            }
            _ => return Err(format!("unsupported resolve argument {arg:?}")),
        }
    }

    let selector = selector.ok_or_else(|| "resolve requires --workflow".to_owned())?;
    validate_ref(&target_ref)?;
    let workflow = select_workflow(workflows, &selector)?;
    if workflow.file == "repository-dispatch.yml" {
        return Err("repository-dispatch.yml cannot dispatch itself".to_owned());
    }
    if !workflow.workflow_dispatch {
        return Err(format!("{} does not expose workflow_dispatch", workflow.file));
    }

    let raw: Value = serde_json::from_str(&inputs_json)
        .map_err(|error| format!("--inputs-json is invalid JSON: {error}"))?;
    let supplied = raw
        .as_object()
        .ok_or_else(|| "--inputs-json must be a JSON object".to_owned())?;
    let normalized = normalize_inputs(workflow, supplied)?;
    let body = serde_json::json!({"ref": target_ref, "inputs": normalized});
    let resolved = ResolvedDispatch {
        workflow: workflow.file.clone(),
        alias: workflow.alias.clone(),
        name: workflow.name.clone(),
        r#ref: target_ref,
        inputs: normalized,
        body,
    };

    let compact = serde_json::to_string(&resolved).map_err(|error| error.to_string())?;
    println!("{compact}");
    if let Some(path) = github_output {
        let body = serde_json::to_string(&resolved.body).map_err(|error| error.to_string())?;
        let lines = format!(
            "workflow={}\nalias={}\nref={}\ninputs={}\nbody={}\n",
            resolved.workflow,
            resolved.alias,
            resolved.r#ref,
            serde_json::to_string(&resolved.inputs).map_err(|error| error.to_string())?,
            body
        );
        fs::write(&path, lines).map_err(|error| format!("{}: {error}", path.display()))?;
    }
    Ok(())
}

fn normalize_inputs(
    workflow: &WorkflowSpec,
    supplied: &Map<String, Value>,
) -> Result<Map<String, Value>, String> {
    let unknown = supplied
        .keys()
        .filter(|key| !workflow.inputs.contains_key(*key))
        .cloned()
        .collect::<Vec<_>>();
    if !unknown.is_empty() {
        return Err(format!(
            "{} received unknown input(s): {}",
            workflow.file,
            unknown.join(", ")
        ));
    }

    let mut normalized = Map::new();
    for (name, spec) in &workflow.inputs {
        let value = match supplied.get(name) {
            Some(value) if !value.is_null() => value.clone(),
            _ => match &spec.default {
                Some(value) => value.clone(),
                None if spec.required => {
                    return Err(format!("{} requires input {name:?}", workflow.file));
                }
                None => continue,
            },
        };
        validate_input_value(&workflow.file, name, spec, &value)?;
        normalized.insert(name.clone(), value);
    }
    Ok(normalized)
}

fn validate_input_value(
    workflow: &str,
    name: &str,
    spec: &InputSpec,
    value: &Value,
) -> Result<(), String> {
    match spec.kind.as_str() {
        "boolean" => {
            if !value.is_boolean() {
                return Err(format!("{workflow} input {name:?} must be boolean"));
            }
        }
        "choice" => {
            let text = value
                .as_str()
                .ok_or_else(|| format!("{workflow} input {name:?} must be a choice string"))?;
            if !spec.options.iter().any(|option| option == text) {
                return Err(format!(
                    "{workflow} input {name:?} must be one of {:?}; got {text:?}",
                    spec.options
                ));
            }
        }
        "string" | "" => {
            if !value.is_string() {
                return Err(format!("{workflow} input {name:?} must be string"));
            }
        }
        other => return Err(format!("{workflow} input {name:?} has unsupported type {other:?}")),
    }
    Ok(())
}

fn load_workflows(root: &Path) -> Result<BTreeMap<String, WorkflowSpec>, String> {
    let workflow_root = root.join(".github/workflows");
    let mut paths = fs::read_dir(&workflow_root)
        .map_err(|error| format!("{}: {error}", workflow_root.display()))?
        .filter_map(|entry| entry.ok().map(|entry| entry.path()))
        .filter(|path| path.extension().and_then(|value| value.to_str()) == Some("yml"))
        .collect::<Vec<_>>();
    paths.sort();

    let mut workflows = BTreeMap::new();
    for path in paths {
        let spec = parse_workflow(&path)?;
        if workflows.insert(spec.file.clone(), spec).is_some() {
            return Err(format!("duplicate workflow path: {}", path.display()));
        }
    }
    Ok(workflows)
}

fn parse_workflow(path: &Path) -> Result<WorkflowSpec, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let file = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| format!("invalid workflow filename: {}", path.display()))?
        .to_owned();
    let alias = file
        .strip_suffix(".yml")
        .unwrap_or(&file)
        .to_owned();
    let name = text
        .lines()
        .find_map(|line| line.strip_prefix("name:").map(|value| unquote(value.trim())))
        .unwrap_or_else(|| alias.clone());

    let lines = text.lines().collect::<Vec<_>>();
    let dispatch_index = lines.iter().position(|line| line.trim_end() == "  workflow_dispatch:");
    let Some(dispatch_index) = dispatch_index else {
        return Ok(WorkflowSpec {
            file,
            alias,
            name,
            workflow_dispatch: false,
            inputs: BTreeMap::new(),
        });
    };

    let mut inputs = BTreeMap::new();
    let mut index = dispatch_index + 1;
    while index < lines.len() {
        let line = lines[index];
        let indent = leading_spaces(line);
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            index += 1;
            continue;
        }
        if indent <= 2 {
            break;
        }
        if indent == 4 && trimmed == "inputs:" {
            index += 1;
            while index < lines.len() {
                let input_line = lines[index];
                let input_indent = leading_spaces(input_line);
                let input_trimmed = input_line.trim();
                if input_trimmed.is_empty() || input_trimmed.starts_with('#') {
                    index += 1;
                    continue;
                }
                if input_indent <= 4 {
                    break;
                }
                if input_indent != 6 || !input_trimmed.ends_with(':') {
                    return Err(format!(
                        "{}:{}: unsupported workflow_dispatch input structure",
                        path.display(),
                        index + 1
                    ));
                }
                let input_name = input_trimmed.trim_end_matches(':').to_owned();
                let (spec, next) = parse_input_spec(path, &lines, index + 1)?;
                inputs.insert(input_name, spec);
                index = next;
            }
            continue;
        }
        index += 1;
    }

    Ok(WorkflowSpec {
        file,
        alias,
        name,
        workflow_dispatch: true,
        inputs,
    })
}

fn parse_input_spec(path: &Path, lines: &[&str], mut index: usize) -> Result<(InputSpec, usize), String> {
    let mut spec = InputSpec {
        kind: "string".to_owned(),
        ..InputSpec::default()
    };
    while index < lines.len() {
        let line = lines[index];
        let indent = leading_spaces(line);
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            index += 1;
            continue;
        }
        if indent <= 6 {
            break;
        }
        if indent != 8 {
            return Err(format!("{}:{}: unsupported input indentation", path.display(), index + 1));
        }
        let (key, raw) = trimmed
            .split_once(':')
            .ok_or_else(|| format!("{}:{}: expected key: value", path.display(), index + 1))?;
        let raw = raw.trim();
        match key {
            "description" => {}
            "required" => spec.required = parse_bool(raw, path, index)?,
            "type" => spec.kind = unquote(raw),
            "default" => spec.default = Some(parse_scalar(raw)),
            "options" if raw.starts_with('[') && raw.ends_with(']') => {
                spec.options = raw[1..raw.len() - 1]
                    .split(',')
                    .map(|value| unquote(value.trim()))
                    .filter(|value| !value.is_empty())
                    .collect();
            }
            "options" if raw.is_empty() => {
                index += 1;
                while index < lines.len() {
                    let option_line = lines[index];
                    if leading_spaces(option_line) != 10 || !option_line.trim_start().starts_with("- ") {
                        break;
                    }
                    spec.options.push(unquote(option_line.trim_start()[2..].trim()));
                    index += 1;
                }
                continue;
            }
            "options" => {
                return Err(format!("{}:{}: unsupported options syntax", path.display(), index + 1));
            }
            other => {
                return Err(format!(
                    "{}:{}: unsupported workflow_dispatch input property {other:?}",
                    path.display(),
                    index + 1
                ));
            }
        }
        index += 1;
    }
    Ok((spec, index))
}

fn validate_catalog(workflows: &BTreeMap<String, WorkflowSpec>) -> Result<(), String> {
    let mut aliases = BTreeSet::new();
    let mut errors = Vec::new();
    for workflow in workflows.values() {
        if !aliases.insert(workflow.alias.clone()) {
            errors.push(format!("duplicate workflow alias: {}", workflow.alias));
        }
        if workflow.file != "repository-dispatch.yml" && !workflow.workflow_dispatch {
            errors.push(format!("{} lacks workflow_dispatch", workflow.file));
        }
        for (name, spec) in &workflow.inputs {
            if spec.kind == "choice" && spec.options.is_empty() {
                errors.push(format!("{} input {name:?} is choice without options", workflow.file));
            }
            if let Some(default) = &spec.default
                && let Err(error) = validate_input_value(&workflow.file, name, spec, default)
            {
                errors.push(format!("invalid default: {error}"));
            }
        }
    }
    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors.join("; "))
    }
}

fn select_workflow<'a>(
    workflows: &'a BTreeMap<String, WorkflowSpec>,
    selector: &str,
) -> Result<&'a WorkflowSpec, String> {
    if let Some(workflow) = workflows.get(selector) {
        return Ok(workflow);
    }
    let normalized = selector.strip_suffix(".yaml").or_else(|| selector.strip_suffix(".yml")).unwrap_or(selector);
    let matches = workflows
        .values()
        .filter(|workflow| workflow.alias == normalized)
        .collect::<Vec<_>>();
    match matches.as_slice() {
        [workflow] => Ok(*workflow),
        [] => Err(format!("unknown workflow {selector:?}; run `asr-workflow-dispatch list`")),
        _ => Err(format!("ambiguous workflow alias {selector:?}")),
    }
}

fn validate_ref(value: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > 255 {
        return Err("dispatch ref must be 1..=255 characters".to_owned());
    }
    if value.starts_with('-')
        || value.contains("..")
        || value.contains("@{")
        || value.ends_with('.')
        || value.ends_with('/')
        || value.chars().any(|ch| ch.is_control() || ch.is_whitespace() || "~^:?*[\\".contains(ch))
    {
        return Err(format!("unsafe or invalid Git ref {value:?}"));
    }
    Ok(())
}

fn parse_scalar(raw: &str) -> Value {
    let text = unquote(raw);
    match text.as_str() {
        "true" => Value::Bool(true),
        "false" => Value::Bool(false),
        _ => Value::String(text),
    }
}

fn parse_bool(raw: &str, path: &Path, index: usize) -> Result<bool, String> {
    match raw {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(format!("{}:{}: expected boolean", path.display(), index + 1)),
    }
}

fn unquote(value: &str) -> String {
    let value = value.trim();
    if value.len() >= 2
        && ((value.starts_with('"') && value.ends_with('"'))
            || (value.starts_with('\'') && value.ends_with('\'')))
    {
        value[1..value.len() - 1].to_owned()
    } else {
        value.to_owned()
    }
}

fn leading_spaces(line: &str) -> usize {
    line.bytes().take_while(|byte| *byte == b' ').count()
}

fn repository_root() -> Result<PathBuf, String> {
    let mut current = env::current_dir().map_err(|error| error.to_string())?;
    loop {
        if current.join(".github/workflows").is_dir() && current.join("Cargo.toml").is_file() {
            return Ok(current);
        }
        if !current.pop() {
            return Err("could not locate repository root".to_owned());
        }
    }
}

fn required_value(args: &mut impl Iterator<Item = String>, flag: &str) -> Result<String, String> {
    args.next()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn reject_extra(mut args: impl Iterator<Item = String>) -> Result<(), String> {
    if let Some(extra) = args.next() {
        Err(format!("unexpected argument {extra:?}"))
    } else {
        Ok(())
    }
}

fn usage() -> String {
    "usage: asr-workflow-dispatch <list|describe|validate|resolve> ...".to_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_refs() {
        assert!(validate_ref("main").is_ok());
        assert!(validate_ref("refs/tags/v1.2.3").is_ok());
        assert!(validate_ref("../main").is_err());
        assert!(validate_ref("bad ref").is_err());
    }

    #[test]
    fn validates_choice() {
        let spec = InputSpec {
            required: false,
            kind: "choice".to_owned(),
            default: Some(Value::String("smoke".to_owned())),
            options: vec!["smoke".to_owned(), "full".to_owned()],
        };
        assert!(validate_input_value("x.yml", "evaluation", &spec, &Value::String("full".to_owned())).is_ok());
        assert!(validate_input_value("x.yml", "evaluation", &spec, &Value::String("bad".to_owned())).is_err());
    }
}
