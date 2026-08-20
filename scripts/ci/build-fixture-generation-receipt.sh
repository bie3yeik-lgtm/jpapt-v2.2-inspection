#!/usr/bin/env bash
set -euo pipefail

generation_id="${1:?generation_id is required}"
source_revision="${2:?source_revision is required}"
hf_bucket="${3:?hf_bucket is required}"
output_json="${4:?output json path is required}"
dry_run="${5:-true}"
execute="${6:-false}"
run_id="${GITHUB_RUN_ID:-local}"
attempt="${GITHUB_RUN_ATTEMPT:-0}"

[[ "$source_revision" =~ ^[0-9a-f]{40}$ ]] || {
  echo "ERROR: source_revision must be a lowercase 40-hex SHA" >&2
  exit 2
}
[[ "$generation_id" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "ERROR: generation_id contains unsupported characters" >&2
  exit 2
}
[[ "$dry_run" == true || "$dry_run" == false ]] || {
  echo "ERROR: dry_run must be true or false" >&2
  exit 2
}
[[ "$execute" == true || "$execute" == false ]] || {
  echo "ERROR: execute must be true or false" >&2
  exit 2
}

if [[ "$execute" == true && "$dry_run" == true ]]; then
  echo "ERROR: execute=true requires dry_run=false" >&2
  exit 2
fi

inspection_id="inspect-${generation_id}-${run_id}-${attempt}"
status="planned"
bucket_run_id=""
notes="plan-only; no Bucket mutation or HF Jobs dispatch"

if [[ "$execute" == true ]]; then
  status="dispatched"
  notes="reviewed execute request; canonical Candidate Request Gateway dispatch is required for HF Jobs"
fi

command -v jq >/dev/null 2>&1 || {
  echo "ERROR: jq is required to build fixture generation receipt" >&2
  exit 2
}

mkdir -p "$(dirname "$output_json")"
jq -n \
  --argjson schema_version 1 \
  --arg generation_id "$generation_id" \
  --arg inspection_id "$inspection_id" \
  --arg source_revision "$source_revision" \
  --arg hf_bucket "$hf_bucket" \
  --arg status "$status" \
  --argjson dry_run "$dry_run" \
  --argjson execute "$execute" \
  --arg bucket_run_id "$bucket_run_id" \
  --arg notes "$notes" \
  '{
    schema_version: $schema_version,
    generation_id: $generation_id,
    inspection_id: $inspection_id,
    source_revision: $source_revision,
    hf_bucket: $hf_bucket,
    status: $status,
    dry_run: $dry_run,
    execute: $execute,
    bucket_run_id: (if ($bucket_run_id | length) > 0 then $bucket_run_id else null end),
    notes: $notes
  }' >"$output_json"

echo "fixture generation receipt: status=$status generation_id=$generation_id inspection_id=$inspection_id"
