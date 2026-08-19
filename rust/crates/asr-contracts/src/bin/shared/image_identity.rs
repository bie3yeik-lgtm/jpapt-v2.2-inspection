#![allow(dead_code)] // Included by multiple binaries; each binary intentionally uses only a subset.

pub fn digest_pinned_image_digest(value: &str, field: &str) -> Result<String, String> {
    if value.is_empty()
        || value.len() > 512
        || !value.is_ascii()
        || value.chars().any(char::is_whitespace)
    {
        return Err(format!(
            "{field} is empty, too long, non-ASCII, or contains whitespace"
        ));
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "./:@_-".contains(ch))
    {
        return Err(format!("{field} contains unsupported characters"));
    }

    let Some((name, digest)) = value.rsplit_once("@sha256:") else {
        return Err(format!(
            "{field} must be immutable and digest-pinned with @sha256:<64 hex>"
        ));
    };
    if name.is_empty() || name.contains('@') {
        return Err(format!("{field} has an invalid image name"));
    }
    if name.starts_with('/') || name.ends_with('/') || name.contains("//") {
        return Err(format!("{field} has an ambiguous image path"));
    }
    if name.split('/').any(|segment| matches!(segment, "." | "..")) {
        return Err(format!(
            "{field} must not contain dot-only image path segments"
        ));
    }
    if digest.len() != 64
        || !digest
            .chars()
            .all(|ch| ch.is_ascii_hexdigit() && !ch.is_ascii_uppercase())
    {
        return Err(format!("{field} has an invalid lowercase sha256 digest"));
    }

    Ok(format!("sha256:{digest}"))
}

pub fn validate_digest_pinned_image(value: &str, field: &str) -> Result<(), String> {
    digest_pinned_image_digest(value, field).map(|_| ())
}

pub fn validate_digest_pinned_image_binding(
    image_ref: &str,
    image_digest: &str,
    field: &str,
) -> Result<(), String> {
    if image_digest.is_empty() {
        return Err(format!("{field} digest must be present"));
    }
    let embedded = digest_pinned_image_digest(image_ref, field)?;
    let Some(expected) = image_digest.strip_prefix("sha256:") else {
        return Err(format!("{field} digest must use sha256:<64 lowercase hex>"));
    };
    if expected.len() != 64
        || !expected
            .chars()
            .all(|ch| ch.is_ascii_hexdigit() && !ch.is_ascii_uppercase())
    {
        return Err(format!("{field} digest must use sha256:<64 lowercase hex>"));
    }
    if embedded != image_digest {
        return Err(format!("{field} ref/digest binding is invalid"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn digest() -> String {
        "a".repeat(64)
    }

    #[test]
    fn accepts_registry_port_namespace_tag_and_digest() {
        let value = format!("registry.example:5000/ns/repo:tag@sha256:{}", digest());
        assert_eq!(
            digest_pinned_image_digest(&value, "image").unwrap(),
            format!("sha256:{}", digest())
        );
    }

    #[test]
    fn rejects_ambiguous_image_paths() {
        for name in [
            "/registry/ns/repo",
            "registry/ns/repo/",
            "registry//ns/repo",
            "registry/./repo",
            "registry/../repo",
        ] {
            let value = format!("{name}@sha256:{}", digest());
            assert!(
                digest_pinned_image_digest(&value, "image").is_err(),
                "{value}"
            );
        }
    }

    #[test]
    fn rejects_uppercase_or_mismatched_digest() {
        let uppercase = format!("registry/ns/repo@sha256:{}", "A".repeat(64));
        assert!(digest_pinned_image_digest(&uppercase, "image").is_err());

        let value = format!("registry/ns/repo@sha256:{}", digest());
        assert!(
            validate_digest_pinned_image_binding(
                &value,
                &format!("sha256:{}", "b".repeat(64)),
                "image"
            )
            .is_err()
        );
    }
}
