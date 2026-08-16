use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

fn main() {
    if let Err(error) = run() {
        eprintln!("asr-catalog: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1).collect::<Vec<_>>();
    let repository_root = if args.first().map(String::as_str) == Some("--repository-root") {
        if args.len() < 2 {
            return Err("--repository-root requires a value".to_owned());
        }
        let root = PathBuf::from(args.remove(1));
        args.remove(0);
        root
    } else {
        PathBuf::from(".")
    };

    let catalog = Catalog::load(&repository_root.join("config/asr-catalog.json"))?;
    match args.as_slice() {
        [command] if command == "summary" => print_summary(&catalog)?,
        [command, field] if command == "fingerprint" => match field.as_str() {
            "catalog_id" => println!("{}", catalog.catalog_id),
            "sha256" => println!("{}", catalog.sha256),
            _ => return Err(format!("unknown fingerprint field {field:?}")),
        },
        [command, profile_id, field] if command == "profile" => {
            let profile = catalog.decoder_profile(profile_id)?;
            match field.as_str() {
                "decoder" => println!("{}", profile.decoder),
                "artifact_contract" => println!("{}", profile.artifact_contract),
                "tokenizer_kind" => println!("{}", profile.tokenizer_kind),
                _ => return Err(format!("unknown profile field {field:?}")),
            }
        }
        [command, profile_set_id, field] if command == "profile-set" => {
            print_profile_set(&catalog, profile_set_id, None, field)?;
        }
        [command, profile_set_id, option, variant, field]
            if command == "profile-set" && option == "--variant" =>
        {
            print_profile_set(&catalog, profile_set_id, Some(variant), field)?;
        }
        _ => return Err(usage().to_owned()),
    }
    Ok(())
}

fn usage() -> &'static str {
    "usage: asr-catalog [--repository-root <path>] summary\n       asr-catalog [--repository-root <path>] fingerprint <catalog_id|sha256>\n       asr-catalog [--repository-root <path>] profile <profile_id> <decoder|artifact_contract|tokenizer_kind>\n       asr-catalog [--repository-root <path>] profile-set <profile_set_id> [--variant <variant>] <profile_id|decoder|artifact_contract|tokenizer_kind|default_variant>"
}

fn print_summary(catalog: &Catalog) -> Result<(), String> {
    println!("ASR runtime catalog: {} {}", catalog.catalog_id, catalog.sha256);
    println!("Runtime profile sets:");
    for (profile_set_id, profile_set) in &catalog.profile_sets {
        let variants = serde_json::to_string(&profile_set.variants).map_err(|error| error.to_string())?;
        println!(
            "- {profile_set_id}: {variants} default={}",
            profile_set.default_variant
        );
    }
    Ok(())
}

fn print_profile_set(
    catalog: &Catalog,
    profile_set_id: &str,
    variant: Option<&String>,
    field: &str,
) -> Result<(), String> {
    let profile_set = catalog.profile_set(profile_set_id)?;
    if field == "default_variant" {
        println!("{}", profile_set.default_variant);
        return Ok(());
    }
    let profile_id = profile_set.profile_id_for(variant.map(String::as_str))?;
    if field == "profile_id" {
        println!("{profile_id}");
        return Ok(());
    }
    let profile = catalog.decoder_profile(profile_id)?;
    match field {
        "decoder" => println!("{}", profile.decoder),
        "artifact_contract" => println!("{}", profile.artifact_contract),
        "tokenizer_kind" => println!("{}", profile.tokenizer_kind),
        _ => return Err(format!("unknown profile-set field {field:?}")),
    }
    Ok(())
}

#[derive(Debug, Deserialize)]
struct CatalogDocument {
    schema_version: u32,
    catalog_id: String,
    decoder_profiles: BTreeMap<String, DecoderProfileDocument>,
    profile_sets: BTreeMap<String, ProfileSetDocument>,
}

#[derive(Debug, Deserialize)]
struct DecoderProfileDocument {
    decoder: String,
    artifact_contract: String,
    tokenizer_kind: String,
    required_artifact_roles: Vec<String>,
    #[serde(default)]
    optional_artifact_roles: Vec<String>,
    features: BTreeMap<String, bool>,
}

#[derive(Debug, Deserialize)]
struct ProfileSetDocument {
    variants: BTreeMap<String, String>,
    default_variant: String,
}

#[derive(Debug)]
struct Catalog {
    catalog_id: String,
    sha256: String,
    decoder_profiles: BTreeMap<String, DecoderProfile>,
    profile_sets: BTreeMap<String, ProfileSet>,
}

#[derive(Debug)]
struct DecoderProfile {
    decoder: String,
    artifact_contract: String,
    tokenizer_kind: String,
}

#[derive(Debug)]
struct ProfileSet {
    variants: BTreeMap<String, String>,
    default_variant: String,
}

impl Catalog {
    fn load(path: &Path) -> Result<Self, String> {
        let bytes = fs::read(path).map_err(|error| format!("{}: {error}", path.display()))?;
        let raw: Value = serde_json::from_slice(&bytes)
            .map_err(|error| format!("failed to parse {}: {error}", path.display()))?;
        let document: CatalogDocument = serde_json::from_value(raw.clone())
            .map_err(|error| format!("invalid ASR catalog {}: {error}", path.display()))?;
        if document.schema_version != 1 {
            return Err("ASR catalog must be a schema_version=1 object".to_owned());
        }
        let catalog_id = nonempty("catalog_id", document.catalog_id)?;
        if document.decoder_profiles.is_empty() {
            return Err("decoder_profiles must be a non-empty object".to_owned());
        }
        if document.profile_sets.is_empty() {
            return Err("profile_sets must be a non-empty object".to_owned());
        }

        let mut decoder_profiles = BTreeMap::new();
        for (profile_id, profile) in document.decoder_profiles {
            let profile_id = nonempty("decoder_profiles key", profile_id)?;
            let decoder = nonempty(
                &format!("decoder_profiles.{profile_id}.decoder"),
                profile.decoder,
            )?;
            let artifact_contract = nonempty(
                &format!("decoder_profiles.{profile_id}.artifact_contract"),
                profile.artifact_contract,
            )?;
            let tokenizer_kind = nonempty(
                &format!("decoder_profiles.{profile_id}.tokenizer_kind"),
                profile.tokenizer_kind,
            )?;
            validate_string_array(
                &format!("decoder_profiles.{profile_id}.required_artifact_roles"),
                &profile.required_artifact_roles,
                true,
            )?;
            validate_string_array(
                &format!("decoder_profiles.{profile_id}.optional_artifact_roles"),
                &profile.optional_artifact_roles,
                false,
            )?;
            if profile.features.keys().any(|key| key.trim().is_empty()) {
                return Err(format!(
                    "decoder_profiles.{profile_id}.features keys must be non-empty strings"
                ));
            }
            decoder_profiles.insert(
                profile_id,
                DecoderProfile {
                    decoder,
                    artifact_contract,
                    tokenizer_kind,
                },
            );
        }

        let mut profile_sets = BTreeMap::new();
        for (profile_set_id, profile_set) in document.profile_sets {
            let profile_set_id = nonempty("profile_sets key", profile_set_id)?;
            if profile_set.variants.is_empty() {
                return Err(format!(
                    "profile_sets.{profile_set_id}.variants must be a non-empty object"
                ));
            }
            let mut variants = BTreeMap::new();
            for (variant, profile_id) in profile_set.variants {
                let variant = nonempty(
                    &format!("profile_sets.{profile_set_id}.variants key"),
                    variant,
                )?;
                let profile_id = nonempty(
                    &format!("profile_sets.{profile_set_id}.variants.{variant}"),
                    profile_id,
                )?;
                if !decoder_profiles.contains_key(&profile_id) {
                    return Err(format!(
                        "profile set {profile_set_id:?} references unknown decoder profile {profile_id:?}"
                    ));
                }
                variants.insert(variant, profile_id);
            }
            let default_variant = nonempty(
                &format!("profile_sets.{profile_set_id}.default_variant"),
                profile_set.default_variant,
            )?;
            if !variants.contains_key(&default_variant) {
                return Err(format!(
                    "profile_sets.{profile_set_id}.default_variant must reference a declared variant"
                ));
            }
            profile_sets.insert(
                profile_set_id,
                ProfileSet {
                    variants,
                    default_variant,
                },
            );
        }

        let canonical = canonical_json(&raw)?;
        let sha256 = format!("{:x}", Sha256::digest(canonical.as_bytes()));
        Ok(Self {
            catalog_id,
            sha256,
            decoder_profiles,
            profile_sets,
        })
    }

    fn decoder_profile(&self, profile_id: &str) -> Result<&DecoderProfile, String> {
        self.decoder_profiles.get(profile_id).ok_or_else(|| {
            format!(
                "unknown decoder profile {profile_id:?}; available={:?}",
                self.decoder_profiles.keys().collect::<Vec<_>>()
            )
        })
    }

    fn profile_set(&self, profile_set_id: &str) -> Result<&ProfileSet, String> {
        self.profile_sets.get(profile_set_id).ok_or_else(|| {
            format!(
                "unknown profile set {profile_set_id:?}; available={:?}",
                self.profile_sets.keys().collect::<Vec<_>>()
            )
        })
    }
}

impl ProfileSet {
    fn profile_id_for(&self, variant: Option<&str>) -> Result<&str, String> {
        let selected = variant.unwrap_or(&self.default_variant);
        self.variants
            .get(selected)
            .map(String::as_str)
            .ok_or_else(|| {
                format!(
                    "unknown runtime variant {selected:?}; available={:?}",
                    self.variants.keys().collect::<Vec<_>>()
                )
            })
    }
}

fn validate_string_array(name: &str, values: &[String], required: bool) -> Result<(), String> {
    if required && values.is_empty() {
        return Err(format!("{name} must be a non-empty string array"));
    }
    if values.iter().any(|value| value.trim().is_empty()) {
        return Err(format!("{name} must contain only non-empty strings"));
    }
    Ok(())
}

fn nonempty(name: &str, value: String) -> Result<String, String> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        Err(format!("{name} must be a non-empty string"))
    } else {
        Ok(trimmed.to_owned())
    }
}

fn canonical_json(value: &Value) -> Result<String, String> {
    fn render(value: &Value, output: &mut String) -> Result<(), serde_json::Error> {
        match value {
            Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {
                output.push_str(&serde_json::to_string(value)?);
            }
            Value::Array(values) => {
                output.push('[');
                for (index, value) in values.iter().enumerate() {
                    if index != 0 {
                        output.push(',');
                    }
                    render(value, output)?;
                }
                output.push(']');
            }
            Value::Object(values) => {
                output.push('{');
                let mut keys = values.keys().collect::<Vec<_>>();
                keys.sort();
                for (index, key) in keys.iter().enumerate() {
                    if index != 0 {
                        output.push(',');
                    }
                    output.push_str(&serde_json::to_string(key)?);
                    output.push(':');
                    render(&values[*key], output)?;
                }
                output.push('}');
            }
        }
        Ok(())
    }

    let mut output = String::new();
    render(value, &mut output).map_err(|error| error.to_string())?;
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_json_sorts_object_keys() {
        let value: Value = serde_json::from_str(r#"{"b":2,"a":{"d":4,"c":3}}"#).unwrap();
        assert_eq!(
            canonical_json(&value).unwrap(),
            r#"{"a":{"c":3,"d":4},"b":2}"#
        );
    }

    #[test]
    fn profile_set_uses_default_variant() {
        let set = ProfileSet {
            variants: BTreeMap::from([
                ("ctc".to_owned(), "ctc-v1".to_owned()),
                ("tdt".to_owned(), "tdt-v1".to_owned()),
            ]),
            default_variant: "ctc".to_owned(),
        };
        assert_eq!(set.profile_id_for(None).unwrap(), "ctc-v1");
    }
}
