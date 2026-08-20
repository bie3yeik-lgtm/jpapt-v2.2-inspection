#!/usr/bin/env bash
set -euo pipefail

source_repository="${1:?source_repository is required}"
source_revision="${2:?source_revision is required}"
hf_bucket="${3:?hf_bucket is required}"
candidate_id="${4:?candidate_id is required}"
validation_mode="${5:?validation_mode is required}"
output_json="${6:?output json path is required}"
dry_run="${7:-true}"
execute="${8:-false}"
hf_target="${HF_TARGET:-parakeet-tdt_ctc-0.6b-ja}"

[[ "$source_repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
  echo "ERROR: source_repository must use owner/name" >&2
  exit 2
}
[[ "$source_revision" =~ ^[0-9a-f]{40}$ ]] || {
  echo "ERROR: source_revision must be a lowercase 40-hex SHA" >&2
  exit 2
}
[[ "$candidate_id" =~ ^candidate-[0-9]{6}$ ]] || {
  echo "ERROR: candidate_id must use candidate-NNNNNN" >&2
  exit 2
}
[[ "$validation_mode" == smoke || "$validation_mode" == parity ]] || {
  echo "ERROR: validation_mode must be smoke or parity" >&2
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

status="planned"
notes="plan-only external DirectML route; Linux HF Jobs smoke is not equivalent evidence"
if [[ "$execute" == true ]]; then
  status="ready_for_execution"
  notes="reviewed execute request for Windows DirectML provider route"
fi

command -v jq >/dev/null 2>&1 || {
  echo "ERROR: jq is required to build Windows DirectML external receipt" >&2
  exit 2
}

mkdir -p "$(dirname "$output_json")"
jq -n \
  --argjson schema_version 1 \
  --arg source_repository "$source_repository" \
  --arg source_revision "$source_revision" \
  --arg hf_bucket "$hf_bucket" \
  --arg candidate_id "$candidate_id" \
  --arg provider_id directml \
  --arg runner_os windows \
  --arg validation_mode "$validation_mode" \
  --arg status "$status" \
  --argjson dry_run "$dry_run" \
  --argjson execute "$execute" \
  --argjson linux_hf_jobs_smoke_equivalent false \
  --arg hf_target "$hf_target" \
  --arg notes "$notes" \
  '{
    schema_version: $schema_version,
    source_repository: $source_repository,
    source_revision: $source_revision,
    hf_bucket: $hf_bucket,
    candidate_id: $candidate_id,
    provider_id: $provider_id,
    runner_os: $runner_os,
    validation_mode: $validation_mode,
    status: $status,
    dry_run: $dry_run,
    execute: $execute,
    linux_hf_jobs_smoke_equivalent: $linux_hf_jobs_smoke_equivalent,
    hf_target: $hf_target,
    notes: $notes
  }' >"$output_json"

echo "windows directml external receipt: status=$status candidate_id=$candidate_id"
