#!/usr/bin/env bash

set -euo pipefail

# -----------------------------------------------------------------------------
# Upload one complete evaluation run to HF Bucket runs/.
#
# Usage:
#
#   scripts/hf/hf-push-run.sh <run-directory>
#
# Required files:
#
#   run-context.json
#   metrics.json
#   samples.jsonl
#   run.parquet
#
# Remote:
#
#   hf://buckets/<HF_BUCKET>/runs/<run-id>/
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
    pwd
)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"
export PARAKEET_ONNX_REPO_ROOT="$ROOT"

log() { printf '[hf-push-run] %s\n' "$*"; }
fail() { printf '[hf-push-run] ERROR: %s\n' "$*" >&2; exit 1; }

require_env() {
    local name="$1"
    [[ -n "${!name:-}" ]] || fail "Required environment variable is not set: $name"
}

normalize_bucket_id() {
    local value="$1" namespace bucket
    value="${value#hf://buckets/}"
    value="${value%/}"
    [[ "$value" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || \
        fail "HF_BUCKET must use canonical namespace/bucket-name format; got: $value"
    namespace="${value%%/*}"
    bucket="${value#*/}"
    if [[ "$namespace" == "." || "$namespace" == ".." || "$bucket" == "." || "$bucket" == ".." ]]; then
        fail "HF_BUCKET must not contain dot path segments; got: $value"
    fi
    printf '%s\n' "$value"
}

require_env HF_TOKEN
require_env HF_BUCKET
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable."
command -v cargo >/dev/null 2>&1 || fail "cargo is unavailable."

RUN_DIRECTORY="${1:-}"
[[ -n "$RUN_DIRECTORY" ]] || fail "Run directory is required. Usage: $0 <run-directory>"
[[ -d "$RUN_DIRECTORY" ]] || fail "Run directory does not exist: $RUN_DIRECTORY"
RUN_DIRECTORY="$(cd -- "$RUN_DIRECTORY" >/dev/null 2>&1 && pwd -P)"

REQUIRED_FILES=(
    "run-context.json"
    "metrics.json"
    "samples.jsonl"
    "run.parquet"
)
for filename in "${REQUIRED_FILES[@]}"; do
    [[ -s "$RUN_DIRECTORY/$filename" ]] || fail "Required run artifact missing or empty: $filename"
done

log "Validating JSON/JSONL contracts with Rust..."
CONTRACT_SUMMARY="$(
    cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
        validate-run "$RUN_DIRECTORY"
)" || fail "Rust run-contract validation failed."

RUN_ID="$(
    printf '%s\n' "$CONTRACT_SUMMARY" \
        | awk -F= '$1 == "run_id" { print $2 }'
)"
JSONL_COUNT="$(
    printf '%s\n' "$CONTRACT_SUMMARY" \
        | awk -F= '$1 == "sample_count" { print $2 }'
)"
[[ -n "$RUN_ID" ]] || fail "Rust contract validator returned no run_id."
[[ "$JSONL_COUNT" =~ ^[0-9]+$ ]] || fail "Rust contract validator returned no valid sample_count."

log "Validating Parquet capsule with Rust..."
CAPSULE_SUMMARY="$(
    cargo run --quiet --locked -p asr-capsule --bin asr-capsule -- \
        validate "$RUN_DIRECTORY/run.parquet" \
        --expected-run-id "$RUN_ID"
)" || fail "Rust capsule validation failed."

PARQUET_COUNT="$(
    printf '%s\n' "$CAPSULE_SUMMARY" \
        | awk -F= '$1 == "sample_count" { print $2 }'
)"
[[ "$PARQUET_COUNT" =~ ^[0-9]+$ ]] || fail "Rust capsule validator returned no valid sample_count."
[[ "$JSONL_COUNT" == "$PARQUET_COUNT" ]] || fail \
    "samples.jsonl and run.parquet contain different sample counts: jsonl=$JSONL_COUNT, parquet=$PARQUET_COUNT"
log "Validated $JSONL_COUNT JSONL/Parquet sample results."

HF_BUCKET_ID="$(normalize_bucket_id "$HF_BUCKET")"
REMOTE="hf://buckets/${HF_BUCKET_ID}/runs/${RUN_ID}"

log "Run ID: $RUN_ID"
log "Source: $RUN_DIRECTORY"
log "Destination: $REMOTE"

# Never use --delete here. Runs are append-oriented durable history.
hf buckets sync \
    --token "$HF_TOKEN" \
    "$RUN_DIRECTORY" \
    "$REMOTE"

log "Run upload completed."
