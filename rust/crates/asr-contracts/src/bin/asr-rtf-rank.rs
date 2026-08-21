use std::env;
use std::fs;
use std::path::PathBuf;

use asr_contracts::rtf_rank::rank_rtf_records;
use serde_json::Value;

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-rtf-rank: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let output = PathBuf::from(args.next().ok_or_else(usage)?);
    let mut diagnostics = None;
    let mut phase = None;
    let mut inputs = Vec::new();
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--diagnostics" => diagnostics = Some(PathBuf::from(args.next().ok_or_else(usage)?)),
            "--phase" => phase = Some(args.next().ok_or_else(usage)?),
            _ if arg.starts_with('-') => return Err(format!("unknown option {arg}; {}", usage())),
            _ => inputs.push(PathBuf::from(arg)),
        }
    }
    if inputs.is_empty() {
        return Err(usage());
    }
    let values = inputs
        .iter()
        .map(|path| {
            let text =
                fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
            let value: Value = serde_json::from_str(&text)
                .map_err(|error| format!("{}: {error}", path.display()))?;
            Ok((path.display().to_string(), value))
        })
        .collect::<Result<Vec<_>, String>>()?;
    let ranked = rank_rtf_records(values, phase.as_deref()).map_err(|error| error.to_string())?;
    let rendered = serde_json::to_string_pretty(&ranked).map_err(|error| error.to_string())?;
    fs::write(&output, format!("{rendered}\n"))
        .map_err(|error| format!("{}: {error}", output.display()))?;
    if let Some(path) = diagnostics {
        let rendered =
            serde_json::to_string_pretty(&ranked.excluded).map_err(|error| error.to_string())?;
        fs::write(&path, format!("{rendered}\n"))
            .map_err(|error| format!("{}: {error}", path.display()))?;
    }
    Ok(())
}

fn usage() -> String {
    "usage: asr-rtf-rank <output.json> [--phase <phase1|pref|probe>] [--diagnostics <excluded.json>] <record.json>...".to_owned()
}
