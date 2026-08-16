#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"
export PARAKEET_ONNX_REPO_ROOT="$ROOT"

log(){ printf '[hf-fetch-candidate] %s\n' "$*"; }
fail(){ printf '[hf-fetch-candidate] ERROR: %s\n' "$*" >&2; exit 1; }
require_env(){ local name="$1"; [[ -n "${!name:-}" ]] || fail "Required environment variable is not set: $name"; }
normalize_bucket_id(){
    local value="$1"
    value="${value#hf://buckets/}"
    value="${value%/}"
    [[ "$value" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format; got: $value"
    printf '%s\n' "$value"
}
validate_candidate_id(){
    local value="$1"
    [[ "$value" =~ ^candidate-[0-9]{6}$ ]] || fail "Candidate ID must use canonical candidate-NNNNNN format; got: $value"
}
append_env(){
    local key="$1" value="$2"
    [[ -n "${GITHUB_ENV:-}" ]] && printf '%s=%s\n' "$key" "$value" >> "$GITHUB_ENV"
}
append_output(){
    local key="$1" value="$2"
    [[ -n "${GITHUB_OUTPUT:-}" ]] && printf '%s=%s\n' "$key" "$value" >> "$GITHUB_OUTPUT"
}

require_env HF_TOKEN
require_env HF_BUCKET
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable."
command -v cargo >/dev/null 2>&1 || fail "cargo is unavailable."

HF_BUCKET_ID="$(normalize_bucket_id "$HF_BUCKET")"
REQUESTED_CANDIDATE_ID="${1:-${CANDIDATE_ID:-}}"
CANDIDATE_RELATIVE_PATH=""
LEGACY_LAYOUT="false"

if [[ -n "$REQUESTED_CANDIDATE_ID" ]]; then
    validate_candidate_id "$REQUESTED_CANDIDATE_ID"
    CANDIDATE_ID="$REQUESTED_CANDIDATE_ID"
    CANDIDATE_RELATIVE_PATH="$CANDIDATE_ID"
else
    listing="$(mktemp)"
    trap 'rm -f "$listing"' EXIT
    REMOTE_ROOT="hf://buckets/${HF_BUCKET_ID}/candidates"
    if ! hf buckets list --token "$HF_TOKEN" "$REMOTE_ROOT" -R -q > "$listing"; then
        fail "failed to list candidate collection: $REMOTE_ROOT"
    fi
    ARGS=(resolve-candidate-location --listing "$listing")
    if [[ -n "${ASR_RUNTIME_VARIANT:-}" ]]; then
        ARGS+=(--runtime-variant "$ASR_RUNTIME_VARIANT")
    fi
    SUMMARY="$(cargo run --quiet --locked -p asr-hf -- "${ARGS[@]}")"
    CANDIDATE_ID="$(printf '%s\n' "$SUMMARY" | sed -n 's/^candidate_id=//p')"
    CANDIDATE_RELATIVE_PATH="$(printf '%s\n' "$SUMMARY" | sed -n 's/^relative_path=//p')"
    LEGACY_LAYOUT="$(printf '%s\n' "$SUMMARY" | sed -n 's/^legacy=//p')"
    validate_candidate_id "$CANDIDATE_ID"
    [[ -n "$CANDIDATE_RELATIVE_PATH" ]] || fail "candidate resolver returned no relative path"
    if [[ "$LEGACY_LAYOUT" == "true" ]]; then
        log "Using read-only legacy candidate fallback: ${CANDIDATE_RELATIVE_PATH}"
    fi
fi

append_env CANDIDATE_ID "$CANDIDATE_ID"
append_output candidate_id "$CANDIDATE_ID"
append_output candidate_relative_path "$CANDIDATE_RELATIVE_PATH"
append_output legacy_candidate_layout "$LEGACY_LAYOUT"

REMOTE="hf://buckets/${HF_BUCKET_ID}/candidates/${CANDIDATE_RELATIVE_PATH}"
LOCAL="$ROOT/.ci/candidate"
STAGING="$ROOT/.ci/candidate.staging"

log "Bucket: $HF_BUCKET_ID"
log "Candidate: $CANDIDATE_ID"
log "Remote: $REMOTE"
log "Local: $LOCAL"

rm -rf "$STAGING"
mkdir -p "$STAGING"
hf buckets sync --token "$HF_TOKEN" "$REMOTE" "$STAGING"

if [[ -z "$(find "$STAGING" -mindepth 1 -print -quit)" ]]; then
    fail "Candidate directory is empty after sync: $STAGING"
fi

ONNX_COUNT="$(find "$STAGING" -type f -name '*.onnx' | wc -l | tr -d ' ')"
[[ "$ONNX_COUNT" -gt 0 ]] || fail "Candidate contains no .onnx files: $CANDIDATE_ID"
[[ -s "$STAGING/metadata.json" ]] || fail "Candidate contains no minimal metadata.json: $CANDIDATE_ID"

printf '%s\n' "$CANDIDATE_ID" > "$STAGING/.candidate-id"
rm -rf "$LOCAL"
mv "$STAGING" "$LOCAL"

log "Candidate files:"
find "$LOCAL" -maxdepth 3 -type f -print | sort
log "ONNX files found: $ONNX_COUNT"
log "Candidate fetch completed."
