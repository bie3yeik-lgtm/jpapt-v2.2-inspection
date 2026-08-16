from pathlib import Path

p = Path("rust/crates/asr-hf/src/allocation.rs")
s = p.read_text()
old = '''pub fn write_allocation_readme(
    output: impl AsRef<Path>,
    allocation_id: &str,
    collection: &str,
    bucket: &str,
    prefix_key: &str,
    prefix: &str,
    sequence: &str,
    allocated_at: &str,
    metadata_json: &str,
) -> Result<()> {
    validate_prefix(prefix)?;
    for (name, value) in [
        ("allocation_id", allocation_id),
        ("collection", collection),
        ("bucket", bucket),
        ("prefix_key", prefix_key),
        ("sequence", sequence),
        ("allocated_at", allocated_at),
    ] {'''
new = '''#[derive(Debug, Clone)]
pub struct AllocationReadme<'a> {
    pub allocation_id: &'a str,
    pub collection: &'a str,
    pub bucket: &'a str,
    pub prefix_key: &'a str,
    pub prefix: &'a str,
    pub sequence: &'a str,
    pub allocated_at: &'a str,
    pub metadata_json: &'a str,
}

pub fn write_allocation_readme(output: impl AsRef<Path>, input: &AllocationReadme<'_>) -> Result<()> {
    validate_prefix(input.prefix)?;
    for (name, value) in [
        ("allocation_id", input.allocation_id),
        ("collection", input.collection),
        ("bucket", input.bucket),
        ("prefix_key", input.prefix_key),
        ("sequence", input.sequence),
        ("allocated_at", input.allocated_at),
    ] {'''
if old not in s:
    raise SystemExit("allocation function marker not found")
s = s.replace(old, new)
s = s.replace(
    "let metadata: Value = serde_json::from_str(metadata_json)?;",
    "let metadata: Value = serde_json::from_str(input.metadata_json)?;",
)
for old_line, new_line in {
    'format!("# {allocation_id}"),': 'format!("# {}", input.allocation_id),',
    'format!("- collection: `{collection}`"),': 'format!("- collection: `{}`", input.collection),',
    'format!("- bucket: `{bucket}`"),': 'format!("- bucket: `{}`", input.bucket),',
    'format!("- prefix_key: `{prefix_key}`"),': 'format!("- prefix_key: `{}`", input.prefix_key),',
    'format!("- resolved_prefix: `{prefix}`"),': 'format!("- resolved_prefix: `{}`", input.prefix),',
    'format!("- sequence: `{sequence}`"),': 'format!("- sequence: `{}`", input.sequence),',
    'format!("- allocated_at: `{allocated_at}`"),': 'format!("- allocated_at: `{}`", input.allocated_at),',
}.items():
    if old_line not in s:
        raise SystemExit(f"README format marker not found: {old_line}")
    s = s.replace(old_line, new_line, 1)
p.write_text(s)

p = Path("rust/crates/asr-hf/src/main.rs")
s = p.read_text()
s = s.replace(
    "load_repository_allocation_catalog, next_sequence_id, write_allocation_readme,",
    "AllocationReadme, load_repository_allocation_catalog, next_sequence_id, write_allocation_readme,",
)
old = '''        } => write_allocation_readme(
            output,
            &allocation_id,
            &collection,
            &bucket,
            &prefix_key,
            &prefix,
            &sequence,
            &allocated_at,
            &metadata_json,
        )?,'''
new = '''        } => write_allocation_readme(
            output,
            &AllocationReadme {
                allocation_id: &allocation_id,
                collection: &collection,
                bucket: &bucket,
                prefix_key: &prefix_key,
                prefix: &prefix,
                sequence: &sequence,
                allocated_at: &allocated_at,
                metadata_json: &metadata_json,
            },
        )?,'''
if old not in s:
    raise SystemExit("main call marker not found")
p.write_text(s.replace(old, new))

p = Path("rust/crates/asr-hf/tests/allocation.rs")
s = p.read_text()
s = s.replace(
    "load_repository_allocation_catalog, next_sequence_id, write_allocation_readme,",
    "AllocationReadme, load_repository_allocation_catalog, next_sequence_id, write_allocation_readme,",
)
start = s.index("    write_allocation_readme(\n        &path,")
end = s.index("    .unwrap();", start)
replacement = '''    write_allocation_readme(
        &path,
        &AllocationReadme {
            allocation_id: "rust-eval-000042",
            collection: "experiments",
            bucket: "owner/bucket",
            prefix_key: "experiment.rust_eval",
            prefix: "rust-eval",
            sequence: "000042",
            allocated_at: "2026-08-17T00:00:00Z",
            metadata_json: r#"{"zeta":"last","alpha":"first"}"#,
        },
    )
'''
s = s[:start] + replacement + s[end:]
p.write_text(s)
