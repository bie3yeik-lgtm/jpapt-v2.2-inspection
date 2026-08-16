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

require_env HF_TOKEN
require_env HF_BUCKET
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable."

CANDIDATE_ID="${1:-${CANDIDATE_ID:-}}"
[[ -n "$CANDIDATE_ID" ]] || fail "Candidate ID is required. Usage: $0 <candidate-id>"
if [[ "$CANDIDATE_ID" == *".."* ]] || [[ "$CANDIDATE_ID" == /* ]] || [[ "$CANDIDATE_ID" == *"\\"* ]]; then
    fail "Unsafe candidate ID: $CANDIDATE_ID"
fi

HF_BUCKET_ID="$(normalize_bucket_id "$HF_BUCKET")"
REMOTE="hf://buckets/${HF_BUCKET_ID}/candidates/${CANDIDATE_ID}"
LOCAL="$ROOT/.ci/candidate"
STAGING="$ROOT/.ci/candidate.staging"

log "Bucket: $HF_BUCKET_ID"
log "Candidate: $CANDIDATE_ID"
log "Remote: $REMOTE"
log "Local: $LOCAL"

# Correctness takes precedence over cache reuse. Candidate discovery may inspect
# tokenizer/config files by path, so stale content from another candidate must
# never survive between materializations.
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
