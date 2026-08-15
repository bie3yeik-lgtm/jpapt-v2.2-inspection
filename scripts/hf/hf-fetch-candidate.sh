#!/usr/bin/env bash

set -euo pipefail

# -----------------------------------------------------------------------------
# Fetch one ONNX candidate directory from the HF Bucket.
#
# Usage:
#
#   scripts/hf/hf-fetch-candidate.sh <candidate-id>
#
# or:
#
#   CANDIDATE_ID=<candidate-id> scripts/hf/hf-fetch-candidate.sh
#
# Remote:
#
#   hf://buckets/<HF_BUCKET>/candidates/<candidate-id>/
#
# Local:
#
#   .ci/candidate/
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
    pwd
)"

ROOT="$(
    cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1
    pwd
)"

cd "$ROOT"

export PARAKEET_ONNX_REPO_ROOT="$ROOT"

log() {
    printf '[hf-fetch-candidate] %s\n' "$*"
}

fail() {
    printf '[hf-fetch-candidate] ERROR: %s\n' "$*" >&2
    exit 1
}

require_env() {
    local name="$1"

    if [[ -z "${!name:-}" ]]; then
        fail "Required environment variable is not set: $name"
    fi
}

normalize_bucket_id() {
    local value="$1"

    value="${value#hf://buckets/}"
    value="${value%/}"

    [[ "$value" == */* ]] \
        || fail \
            "HF_BUCKET must use namespace/bucket-name format; got: $value"

    printf '%s\n' "$value"
}

require_env HF_TOKEN
require_env HF_BUCKET

command -v hf >/dev/null 2>&1 \
    || fail "hf CLI is unavailable."

CANDIDATE_ID="${1:-${CANDIDATE_ID:-}}"

[[ -n "$CANDIDATE_ID" ]] \
    || fail \
        "Candidate ID is required. Usage: $0 <candidate-id>"

if [[ "$CANDIDATE_ID" == *".."* ]] \
    || [[ "$CANDIDATE_ID" == /* ]] \
    || [[ "$CANDIDATE_ID" == *"\\"* ]]; then
    fail "Unsafe candidate ID: $CANDIDATE_ID"
fi

HF_BUCKET_ID="$(normalize_bucket_id "$HF_BUCKET")"
HF_BUCKET_URI="hf://buckets/${HF_BUCKET_ID}"

REMOTE="${HF_BUCKET_URI}/candidates/${CANDIDATE_ID}"
LOCAL="$ROOT/.ci/candidate"

mkdir -p "$LOCAL"

log "Bucket: $HF_BUCKET_ID"
log "Candidate: $CANDIDATE_ID"
log "Remote: $REMOTE"
log "Local: $LOCAL"

# Deliberately do not use --delete.
#
# GitHub Actions cache may already contain reusable candidate content,
# and ordinary sync should only update files that differ.
hf buckets sync \
    --token "$HF_TOKEN" \
    "$REMOTE" \
    "$LOCAL"

if [[ -z "$(find "$LOCAL" -mindepth 1 -print -quit)" ]]; then
    fail \
        "Candidate directory is empty after sync: $LOCAL"
fi

ONNX_COUNT="$(
    find "$LOCAL" \
        -type f \
        -name '*.onnx' \
        | wc -l \
        | tr -d ' '
)"

if [[ "$ONNX_COUNT" -eq 0 ]]; then
    fail \
        "Candidate contains no .onnx files: $CANDIDATE_ID"
fi

printf '%s\n' "$CANDIDATE_ID" \
    > "$LOCAL/.candidate-id"

log "Candidate files:"
find "$LOCAL" \
    -maxdepth 3 \
    -type f \
    -print \
    | sort

log "ONNX files found: $ONNX_COUNT"
log "Candidate fetch completed."
