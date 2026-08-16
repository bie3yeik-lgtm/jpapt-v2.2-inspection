use serde_json::{Map, Value};

use crate::error::{ContractError, Result};

pub struct EmbeddedSchema {
    name: &'static str,
    root: Value,
}

impl EmbeddedSchema {
    pub fn parse(name: &'static str, source: &'static str) -> Result<Self> {
        let root: Value = serde_json::from_str(source).map_err(|error| {
            ContractError::validation(format!("embedded schema {name} is invalid JSON: {error}"))
        })?;
        if !root.is_object() {
            return Err(ContractError::validation(format!(
                "embedded schema {name} root must be an object"
            )));
        }
        Ok(Self { name, root })
    }

    pub fn validate(&self, instance: &Value) -> Result<()> {
        validate_node(instance, &self.root, &self.root, "$", self.name)
    }
}

fn validate_node(
    instance: &Value,
    schema: &Value,
    root: &Value,
    path: &str,
    schema_name: &str,
) -> Result<()> {
    let schema_object = schema.as_object().ok_or_else(|| {
        ContractError::validation(format!(
            "schema {schema_name} contains non-object schema node at {path}"
        ))
    })?;

    if let Some(reference) = schema_object.get("$ref").and_then(Value::as_str) {
        let target = resolve_local_ref(root, reference).ok_or_else(|| {
            ContractError::validation(format!(
                "schema {schema_name} contains unresolved local reference {reference:?}"
            ))
        })?;
        return validate_node(instance, target, root, path, schema_name);
    }

    if let Some(expected) = schema_object.get("const")
        && instance != expected
    {
        return violation(schema_name, path, format!("must equal constant {expected}"));
    }

    if let Some(values) = schema_object.get("enum").and_then(Value::as_array)
        && !values.iter().any(|value| value == instance)
    {
        return violation(
            schema_name,
            path,
            format!("must be one of {}", Value::Array(values.clone())),
        );
    }

    if let Some(type_schema) = schema_object.get("type") {
        validate_type(instance, type_schema, schema_name, path)?;
    }

    if let Some(min_length) = schema_object.get("minLength").and_then(Value::as_u64) {
        let value = instance.as_str().ok_or_else(|| {
            ContractError::validation(format!(
                "schema={schema_name}; instance_path={path}; minLength applies to strings"
            ))
        })?;
        if value.chars().count() < min_length as usize {
            return violation(
                schema_name,
                path,
                format!("string length must be at least {min_length}"),
            );
        }
    }

    if let Some(pattern) = schema_object.get("pattern").and_then(Value::as_str) {
        let value = instance.as_str().ok_or_else(|| {
            ContractError::validation(format!(
                "schema={schema_name}; instance_path={path}; pattern applies to strings"
            ))
        })?;
        if !matches_supported_pattern(pattern, value)? {
            return violation(
                schema_name,
                path,
                format!("string does not match required pattern {pattern:?}"),
            );
        }
    }

    if let Some(minimum) = schema_object.get("minimum").and_then(Value::as_f64) {
        let value = instance.as_f64().ok_or_else(|| {
            ContractError::validation(format!(
                "schema={schema_name}; instance_path={path}; minimum applies to numbers"
            ))
        })?;
        if value < minimum {
            return violation(
                schema_name,
                path,
                format!("number must be >= {minimum}"),
            );
        }
    }

    if let Some(maximum) = schema_object.get("maximum").and_then(Value::as_f64) {
        let value = instance.as_f64().ok_or_else(|| {
            ContractError::validation(format!(
                "schema={schema_name}; instance_path={path}; maximum applies to numbers"
            ))
        })?;
        if value > maximum {
            return violation(
                schema_name,
                path,
                format!("number must be <= {maximum}"),
            );
        }
    }

    if let Some(object) = instance.as_object() {
        validate_object(object, schema_object, root, path, schema_name)?;
    }

    if let Some(array) = instance.as_array()
        && let Some(item_schema) = schema_object.get("items")
    {
        for (index, item) in array.iter().enumerate() {
            validate_node(
                item,
                item_schema,
                root,
                &format!("{path}[{index}]"),
                schema_name,
            )?;
        }
    }

    Ok(())
}

fn validate_type(instance: &Value, type_schema: &Value, schema_name: &str, path: &str) -> Result<()> {
    let allowed = match type_schema {
        Value::String(value) => vec![value.as_str()],
        Value::Array(values) => values
            .iter()
            .map(|value| {
                value.as_str().ok_or_else(|| {
                    ContractError::validation(format!(
                        "schema {schema_name} contains non-string type entry at {path}"
                    ))
                })
            })
            .collect::<Result<Vec<_>>>()?,
        _ => {
            return Err(ContractError::validation(format!(
                "schema {schema_name} contains invalid type declaration at {path}"
            )))
        }
    };

    if allowed.iter().any(|kind| instance_matches_type(instance, kind)) {
        return Ok(());
    }

    violation(
        schema_name,
        path,
        format!("has wrong JSON type; expected one of {allowed:?}"),
    )
}

fn instance_matches_type(instance: &Value, kind: &str) -> bool {
    match kind {
        "object" => instance.is_object(),
        "array" => instance.is_array(),
        "string" => instance.is_string(),
        "integer" => instance.as_i64().is_some() || instance.as_u64().is_some(),
        "number" => instance.is_number(),
        "boolean" => instance.is_boolean(),
        "null" => instance.is_null(),
        _ => false,
    }
}

fn validate_object(
    instance: &Map<String, Value>,
    schema: &Map<String, Value>,
    root: &Value,
    path: &str,
    schema_name: &str,
) -> Result<()> {
    if let Some(required) = schema.get("required").and_then(Value::as_array) {
        for item in required {
            let key = item.as_str().ok_or_else(|| {
                ContractError::validation(format!(
                    "schema {schema_name} has non-string required entry at {path}"
                ))
            })?;
            if !instance.contains_key(key) {
                return violation(
                    schema_name,
                    path,
                    format!("is missing required property {key:?}"),
                );
            }
        }
    }

    let properties = schema
        .get("properties")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();

    for (key, value) in instance {
        if let Some(property_schema) = properties.get(key) {
            validate_node(
                value,
                property_schema,
                root,
                &format!("{path}.{key}"),
                schema_name,
            )?;
            continue;
        }

        match schema.get("additionalProperties") {
            Some(Value::Bool(false)) => {
                return violation(
                    schema_name,
                    path,
                    format!("contains unknown property {key:?}"),
                );
            }
            Some(Value::Object(_)) => validate_node(
                value,
                schema.get("additionalProperties").expect("checked above"),
                root,
                &format!("{path}.{key}"),
                schema_name,
            )?,
            _ => {}
        }
    }

    Ok(())
}

fn resolve_local_ref<'a>(root: &'a Value, reference: &str) -> Option<&'a Value> {
    if !reference.starts_with("#/") {
        return None;
    }
    let mut current = root;
    for raw in reference.trim_start_matches("#/").split('/') {
        let key = raw.replace("~1", "/").replace("~0", "~");
        current = current.get(&key)?;
    }
    Some(current)
}

fn matches_supported_pattern(pattern: &str, value: &str) -> Result<bool> {
    let result = match pattern {
        "^[A-Fa-f0-9]{64}$" => value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit()),
        "^[A-Fa-f0-9]{7,64}$" => {
            (7..=64).contains(&value.len()) && value.bytes().all(|byte| byte.is_ascii_hexdigit())
        }
        "^config-[0-9]{6}$" => {
            value.len() == 13
                && value.starts_with("config-")
                && value[7..].bytes().all(|byte| byte.is_ascii_digit())
        }
        other => {
            return Err(ContractError::validation(format!(
                "embedded schema uses unsupported regex pattern {other:?}; extend asr-contracts before accepting this schema change"
            )))
        }
    };
    Ok(result)
}

fn violation<T>(schema_name: &str, path: &str, message: String) -> Result<T> {
    Err(ContractError::validation(format!(
        "{message}; schema={schema_name}; instance_path={path}"
    )))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_required_and_additional_properties() {
        let schema = EmbeddedSchema::parse(
            "test",
            r#"{"type":"object","additionalProperties":false,"required":["id"],"properties":{"id":{"type":"string","minLength":1}}}"#,
        )
        .unwrap();
        schema.validate(&serde_json::json!({"id":"ok"})).unwrap();
        assert!(schema.validate(&serde_json::json!({"id":"ok","extra":1})).is_err());
    }

    #[test]
    fn validates_local_refs_and_sha_pattern() {
        let schema = EmbeddedSchema::parse(
            "test",
            r##"{"type":"object","required":["sha"],"properties":{"sha":{"$ref":"#/$defs/sha"}},"$defs":{"sha":{"type":"string","pattern":"^[A-Fa-f0-9]{64}$"}}}"##,
        )
        .unwrap();
        schema.validate(&serde_json::json!({"sha":"a".repeat(64)})).unwrap();
        assert!(schema.validate(&serde_json::json!({"sha":"bad"})).is_err());
    }
}
