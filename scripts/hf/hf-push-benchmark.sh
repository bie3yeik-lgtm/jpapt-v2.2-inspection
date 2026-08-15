#!/usr/bin/env bash

set -euo pipefail

# -----------------------------------------------------------------------------
# Upload one lightweight metrics.json document to HF Bucket benchmarks/.
#
# Usage:
#
#   scripts/hf/hf-push-benchmark.sh \
#       <metrics.json> \
#       <benchmark-name>
#
# Example:
#
#   scripts/hf/hf-push-benchmark.sh \
#       results/macos-coreml/metrics.json \
#       coreml
#
# Destination:
#
#   hf://buckets/<HF_BUCKET>/
#       benchmarks/
#           <candidate-id>/
#               <benchmark-name>/
#                   <run-id>.json
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
    printf '[hf-push-benchmark] %s\n' "$*"
}

fail() {
    printf '[hf-push-benchmark] ERROR: %s\n' "$*" >&2
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

validate_path_component() {
    local name="$1"
    local value="$2"

    [[ -n "$value" ]] \
        || fail "$name must not be empty."

    if [[ "$value" == *"/"* ]] \
        || [[ "$value" == *"\\"* ]] \
        || [[ "$value" == *".."* ]]; then
        fail "Unsafe $name: $value"
    fi
}

require_env HF_TOKEN
require_env HF_BUCKET

command -v hf >/dev/null 2>&1 \
    || fail "hf CLI is unavailable."

command -v python >/dev/null 2>&1 \
    || fail "python is unavailable."

METRICS_PATH="${1:-}"
BENCHMARK_NAME="${2:-${BENCHMARK_NAME:-}}"

[[ -n "$METRICS_PATH" ]] \
    || fail \
        "metrics.json path is required."

[[ -n "$BENCHMARK_NAME" ]] \
    || fail \
        "benchmark name is required."

validate_path_component \
    "benchmark name" \
    "$BENCHMARK_NAME"

METRICS_PATH="$(
    python - "$METRICS_PATH" <<'PY'
import sys
from pathlib import Path

print(
    Path(sys.argv[1])
    .expanduser()
    .resolve()
)
PY
)"

[[ -s "$METRICS_PATH" ]] \
    || fail \
        "metrics.json does not exist or is empty: $METRICS_PATH"

readarray -t IDENTITIES < <(
    python - "$METRICS_PATH" <<'PY'
import json
import sys
from pathlib import Path

with Path(sys.argv[1]).open(
    "r",
    encoding="utf-8",
) as file:
    value = json.load(file)

run_id = value.get("run_id")

candidate = value.get(
    "candidate",
    {},
)

candidate_id = candidate.get(
    "candidate_id"
)

if not isinstance(run_id, str) or not run_id:
    raise SystemExit(
        "metrics.json has no valid run_id"
    )

if not isinstance(candidate_id, str) or not candidate_id:
    raise SystemExit(
        "metrics.json has no valid candidate.candidate_id"
    )

print(run_id)
print(candidate_id)
PY
)

RUN_ID="${IDENTITIES[0]}"
CANDIDATE_ID="${IDENTITIES[1]}"

validate_path_component \
    "run ID" \
    "$RUN_ID"

validate_path_component \
    "candidate ID" \
    "$CANDIDATE_ID"

if command -v uv >/dev/null 2>&1; then
    log "Validating benchmark JSON Schema..."

    uv run python - "$METRICS_PATH" <<'PY'
import json
import sys
from pathlib import Path

from parakeet_onnx.evaluation import (
    validate_benchmark,
)

with Path(sys.argv[1]).open(
    "r",
    encoding="utf-8",
) as file:
    validate_benchmark(
        json.load(file)
    )
PY
else
    log \
        "uv unavailable; skipped project benchmark schema validation."
fi

HF_BUCKET_ID="$(normalize_bucket_id "$HF_BUCKET")"

REMOTE="hf://buckets/${HF_BUCKET_ID}/benchmarks/${CANDIDATE_ID}/${BENCHMARK_NAME}/${RUN_ID}.json"

log "Candidate: $CANDIDATE_ID"
log "Benchmark: $BENCHMARK_NAME"
log "Run ID: $RUN_ID"
log "Source: $METRICS_PATH"
log "Destination: $REMOTE"

hf buckets cp \
    --token "$HF_TOKEN" \
    "$METRICS_PATH" \
    "$REMOTE"

log "Benchmark upload completed."
