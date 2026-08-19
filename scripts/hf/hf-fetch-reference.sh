#!/usr/bin/env bash

set -euo pipefail

# -----------------------------------------------------------------------------
# Fetch canonical evaluation reference assets from the HF Bucket.
#
# Remote:
#
#   hf://buckets/<HF_BUCKET>/reference/
#
# Local:
#
#   .ci/reference/
#
# The reference directory may contain:
#
#   manifests/
#   outputs/
#   tensors/
#   metadata/
#
# It may contain large artifacts and therefore must not be committed to Git.
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
    printf '[hf-fetch-reference] %s\n' "$*"
}

fail() {
    printf '[hf-fetch-reference] ERROR: %s\n' "$*" >&2
    exit 1
}

require_env() {
    local name="$1"

    if [[ -z "${!name:-}" ]]; then
        fail "Required environment variable is not set: $name"
    fi
}

normalize_bucket_id() {
    local value="$1" namespace bucket

    value="${value#hf://buckets/}"
    value="${value%/}"

    [[ "$value" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] \
        || fail \
            "HF_BUCKET must use canonical namespace/bucket-name format; got: $value"

    namespace="${value%%/*}"
    bucket="${value#*/}"
    if [[ "$namespace" == "." || "$namespace" == ".." || "$bucket" == "." || "$bucket" == ".." ]]; then
        fail "HF_BUCKET must not contain dot path segments; got: $value"
    fi

    printf '%s\n' "$value"
}

require_env HF_TOKEN
require_env HF_BUCKET

command -v hf >/dev/null 2>&1 \
    || fail "hf CLI is unavailable."

HF_BUCKET_ID="$(normalize_bucket_id "$HF_BUCKET")"
HF_BUCKET_URI="hf://buckets/${HF_BUCKET_ID}"

REMOTE="${HF_BUCKET_URI}/reference"
LOCAL="$ROOT/.ci/reference"

mkdir -p "$LOCAL"

log "Bucket: $HF_BUCKET_ID"
log "Remote: $REMOTE"
log "Local: $LOCAL"

# No --delete:
#
# This preserves cache-restored files that are not part of the current
# transfer while allowing changed reference files to be updated.
hf buckets sync \
    --token "$HF_TOKEN" \
    "$REMOTE" \
    "$LOCAL"

if [[ -z "$(find "$LOCAL" -mindepth 1 -print -quit)" ]]; then
    fail \
        "Reference directory is empty after sync: $LOCAL"
fi

log "Reference fetch completed."
