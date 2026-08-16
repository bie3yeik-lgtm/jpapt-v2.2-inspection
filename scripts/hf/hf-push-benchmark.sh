#!/usr/bin/env bash
set -euo pipefail

# Upload one validated metrics.json document to HF Bucket benchmarks/.
# Canonical benchmark validation and identity extraction are owned by Rust.
# The official hf CLI remains the transport boundary.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-push-benchmark] %s\n' "$*"; }
fail(){ printf '[hf-push-benchmark] ERROR: %s\n' "$*" >&2; exit 1; }

require_env() {
    local name="$1"
    [[ -n "${!name:-}" ]] || fail "Required environment variable is not set: $name"
}

normalize_bucket_id() {
    local value="$1"
    value="${value#hf://buckets/}"
    value="${value%/}"
    [[ "$value" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format; got: $value"
    printf '%s\n' "$value"
}

validate_path_component() {
    local name="$1"
    local value="$2"
    [[ -n "$value" ]] || fail "$name must not be empty."
    if [[ "$value" == *"/"* ]] || [[ "$value" == *"\\"* ]] || [[ "$value" == *".."* ]]; then
        fail "Unsafe $name: $value"
    fi
}

require_env HF_TOKEN
require_env HF_BUCKET
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable."
command -v cargo >/dev/null 2>&1 || fail "cargo is unavailable for Rust benchmark validation."

METRICS_PATH="${1:-}"
BENCHMARK_NAME="${2:-${BENCHMARK_NAME:-}}"
[[ -n "$METRICS_PATH" ]] || fail "metrics.json path is required. Usage: $0 <metrics.json> <benchmark-name>"
[[ -n "$BENCHMARK_NAME" ]] || fail "benchmark name is required. Usage: $0 <metrics.json> <benchmark-name>"
validate_path_component "benchmark name" "$BENCHMARK_NAME"

log "Validating benchmark and resolving upload identity with Rust..."
SUMMARY="$(
    cargo run --quiet --locked \
        -p asr-contracts \
        --bin asr-benchmark \
        -- \
        "$METRICS_PATH"
)"

METRICS_PATH="$(printf '%s\n' "$SUMMARY" | sed -n 's/^metrics_path=//p')"
RUN_ID="$(printf '%s\n' "$SUMMARY" | sed -n 's/^run_id=//p')"
CANDIDATE_ID="$(printf '%s\n' "$SUMMARY" | sed -n 's/^candidate_id=//p')"

[[ -n "$METRICS_PATH" ]] || fail "Rust benchmark inspector did not return metrics_path."
[[ -n "$RUN_ID" ]] || fail "Rust benchmark inspector did not return run_id."
[[ -n "$CANDIDATE_ID" ]] || fail "Rust benchmark inspector did not return candidate_id."
[[ -s "$METRICS_PATH" ]] || fail "metrics.json does not exist or is empty: $METRICS_PATH"

validate_path_component "run ID" "$RUN_ID"
validate_path_component "candidate ID" "$CANDIDATE_ID"

HF_BUCKET_ID="$(normalize_bucket_id "$HF_BUCKET")"
REMOTE="hf://buckets/${HF_BUCKET_ID}/benchmarks/${CANDIDATE_ID}/${BENCHMARK_NAME}/${RUN_ID}.json"

log "Candidate: $CANDIDATE_ID"
log "Benchmark: $BENCHMARK_NAME"
log "Run ID: $RUN_ID"
log "Source: $METRICS_PATH"
log "Destination: $REMOTE"

hf buckets cp --token "$HF_TOKEN" "$METRICS_PATH" "$REMOTE"

log "Benchmark upload completed."
