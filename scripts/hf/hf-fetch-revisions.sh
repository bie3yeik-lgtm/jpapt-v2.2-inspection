#!/usr/bin/env bash

set -euo pipefail

# Fetch the selected immutable HF revision-lock configuration.
#
# Normalized remote layout:
#   config/current.json
#   config/versions/config-NNNNNN/
#       reference.json
#       evaluation-schema.json
#       datasets-lock.json
#       runtime.json
#
# JSON/config selection and revision validation are owned by the Rust
# asr-contracts CLI. The official hf CLI remains the transport boundary.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log() { printf '[hf-fetch-revisions] %s\n' "$*"; }
fail() { printf '[hf-fetch-revisions] ERROR: %s\n' "$*" >&2; exit 1; }

require_env() {
    local name="$1"
    [[ -n "${!name:-}" ]] || fail "Required environment variable is not set: $name"
}

contracts() {
    cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- "$@"
}

require_env HF_TOKEN
require_env HF_BUCKET
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v cargo >/dev/null 2>&1 || fail "cargo is unavailable"

HF_BUCKET_ID="${HF_BUCKET#hf://buckets/}"
HF_BUCKET_ID="${HF_BUCKET_ID%/}"
[[ "$HF_BUCKET_ID" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format"
HF_BUCKET_URI="hf://buckets/${HF_BUCKET_ID}"

LOCAL_CONFIG_ROOT="$ROOT/.ci/hf/config"
LOCAL_ROOT="$LOCAL_CONFIG_ROOT/revisions"
mkdir -p "$LOCAL_ROOT"
rm -f "$LOCAL_ROOT/runtime.json"

CURRENT_REMOTE="${HF_BUCKET_URI}/config/current.json"
CURRENT_LOCAL="$LOCAL_CONFIG_ROOT/current.json"
CURRENT_TMP="${CURRENT_LOCAL}.tmp"
RESOLVED_LOCAL="$LOCAL_CONFIG_ROOT/resolved.json"

log "Bucket: $HF_BUCKET_ID"
log "Fetching configuration pointer: $CURRENT_REMOTE"
rm -f "$CURRENT_TMP"
hf buckets cp --token "$HF_TOKEN" "$CURRENT_REMOTE" "$CURRENT_TMP"
[[ -s "$CURRENT_TMP" ]] || fail "Downloaded config/current.json is empty"
mv -f "$CURRENT_TMP" "$CURRENT_LOCAL"

RESOLVE_ARGS=(
    resolve-config
    --current "$CURRENT_LOCAL"
    --resolved "$RESOLVED_LOCAL"
)
if [[ -n "${HF_CONFIG_VERSION:-}" ]]; then
    RESOLVE_ARGS+=(--override "$HF_CONFIG_VERSION")
fi
CONFIG_VERSION="$(contracts "${RESOLVE_ARGS[@]}")"
[[ "$CONFIG_VERSION" =~ ^config-[0-9]{6}$ ]] || fail "Resolved config version is invalid: $CONFIG_VERSION"

REMOTE_ROOT="${HF_BUCKET_URI}/config/versions/${CONFIG_VERSION}"
REQUIRED_FILES=("reference.json" "evaluation-schema.json" "datasets-lock.json" "runtime.json")

log "Selected config version: $CONFIG_VERSION"
log "Revision source: $REMOTE_ROOT"

fetch_json() {
    local filename="$1"
    local source_uri="${REMOTE_ROOT}/${filename}"
    local destination="$LOCAL_ROOT/$filename"
    local temporary="${destination}.tmp"
    rm -f "$temporary"
    if ! hf buckets cp --token "$HF_TOKEN" "$source_uri" "$temporary" >/dev/null 2>&1; then
        rm -f "$temporary"
        fail "Required config document is missing: $filename"
    fi
    [[ -s "$temporary" ]] || fail "Downloaded config document is empty: $filename"
    mv -f "$temporary" "$destination"
    log "Fetched: $filename"
}

for filename in "${REQUIRED_FILES[@]}"; do
    fetch_json "$filename"
done

log "Validating revision bundle with Rust asr-contracts..."
contracts validate-revisions --root "$LOCAL_ROOT"

log "Revision-lock fetch completed."
