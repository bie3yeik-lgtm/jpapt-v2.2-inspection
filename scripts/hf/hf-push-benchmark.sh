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
#
# Required environment variables:
#
#   HF_TOKEN
#   HF_BUCKET
#
# HF_BUCKET format:
#
#   namespace/bucket-name
#
# or:
#
#   hf://buckets/namespace/bucket-name
#
# Portability:
#
# - Linux Bash
# - Git Bash on Windows
# - macOS system Bash 3.x
#
# In particular, this script intentionally does NOT use Bash 4-only
# `readarray` / `mapfile`.
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


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

log() {
    printf '[hf-push-benchmark] %s\n' "$*"
}

fail() {
    printf '[hf-push-benchmark] ERROR: %s\n' "$*" >&2
    exit 1
}


# -----------------------------------------------------------------------------
# Preconditions
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Arguments
# -----------------------------------------------------------------------------

METRICS_PATH="${1:-}"
BENCHMARK_NAME="${2:-${BENCHMARK_NAME:-}}"

[[ -n "$METRICS_PATH" ]] \
    || fail \
        "metrics.json path is required. Usage: $0 <metrics.json> <benchmark-name>"

[[ -n "$BENCHMARK_NAME" ]] \
    || fail \
        "benchmark name is required. Usage: $0 <metrics.json> <benchmark-name>"

validate_path_component \
    "benchmark name" \
    "$BENCHMARK_NAME"


# -----------------------------------------------------------------------------
# Resolve metrics path
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Read benchmark identity
#
# Do NOT use:
#
#   readarray
#   mapfile
#
# because macOS system Bash is commonly Bash 3.x.
#
# Python emits exactly two lines:
#
#   <run-id>
#   <candidate-id>
# -----------------------------------------------------------------------------

IDENTITIES="$(
    python - "$METRICS_PATH" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

with path.open(
    "r",
    encoding="utf-8",
) as file:
    value = json.load(file)

if not isinstance(value, dict):
    raise SystemExit(
        "metrics.json root must be a JSON object"
    )

run_id = value.get("run_id")

candidate = value.get(
    "candidate",
    {},
)

if not isinstance(candidate, dict):
    raise SystemExit(
        "metrics.json candidate must be a JSON object"
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

# Newlines in these identity fields would make the shell-side
# two-line protocol ambiguous.
if "\n" in run_id or "\r" in run_id:
    raise SystemExit(
        "metrics.json run_id contains a newline"
    )

if "\n" in candidate_id or "\r" in candidate_id:
    raise SystemExit(
        "metrics.json candidate.candidate_id contains a newline"
    )

print(run_id)
print(candidate_id)
PY
)"


RUN_ID="$(
    printf '%s\n' "$IDENTITIES" \
        | sed -n '1p'
)"

CANDIDATE_ID="$(
    printf '%s\n' "$IDENTITIES" \
        | sed -n '2p'
)"


[[ -n "$RUN_ID" ]] \
    || fail \
        "Unable to read run_id from metrics.json."

[[ -n "$CANDIDATE_ID" ]] \
    || fail \
        "Unable to read candidate.candidate_id from metrics.json."


validate_path_component \
    "run ID" \
    "$RUN_ID"

validate_path_component \
    "candidate ID" \
    "$CANDIDATE_ID"


# -----------------------------------------------------------------------------
# Validate benchmark JSON using the project's canonical schema implementation.
#
# Prefer uv when available because local development commonly uses the locked
# uv environment.
#
# GitHub Actions currently installs this project into the active Python
# environment directly, so ordinary `python` validation is also supported.
# -----------------------------------------------------------------------------

validate_benchmark_with_python() {
    local python_command="$1"

    "$python_command" - "$METRICS_PATH" <<'PY'
import json
import sys
from pathlib import Path

from parakeet_onnx.evaluation import (
    validate_benchmark,
)

path = Path(sys.argv[1])

with path.open(
    "r",
    encoding="utf-8",
) as file:
    value = json.load(file)

validate_benchmark(value)

print(
    "[hf-push-benchmark] benchmark schema validation passed"
)
PY
}


if command -v uv >/dev/null 2>&1; then
    log "Validating benchmark JSON Schema with uv..."

    uv run python - "$METRICS_PATH" <<'PY'
import json
import sys
from pathlib import Path

from parakeet_onnx.evaluation import (
    validate_benchmark,
)

path = Path(sys.argv[1])

with path.open(
    "r",
    encoding="utf-8",
) as file:
    value = json.load(file)

validate_benchmark(value)

print(
    "[hf-push-benchmark] benchmark schema validation passed"
)
PY

else
    log "uv unavailable; validating with active Python environment..."

    python - "$METRICS_PATH" <<'PY'
import json
import sys
from pathlib import Path

try:
    from parakeet_onnx.evaluation import (
        validate_benchmark,
    )
except ImportError as exc:
    raise SystemExit(
        "parakeet_onnx is unavailable in the active Python environment; "
        "cannot validate benchmark schema"
    ) from exc

path = Path(sys.argv[1])

with path.open(
    "r",
    encoding="utf-8",
) as file:
    value = json.load(file)

validate_benchmark(value)

print(
    "[hf-push-benchmark] benchmark schema validation passed"
)
PY
fi


# -----------------------------------------------------------------------------
# Resolve HF Bucket destination
# -----------------------------------------------------------------------------

HF_BUCKET_ID="$(
    normalize_bucket_id "$HF_BUCKET"
)"

REMOTE="$(
    printf \
        'hf://buckets/%s/benchmarks/%s/%s/%s.json' \
        "$HF_BUCKET_ID" \
        "$CANDIDATE_ID" \
        "$BENCHMARK_NAME" \
        "$RUN_ID"
)"


log "Candidate: $CANDIDATE_ID"
log "Benchmark: $BENCHMARK_NAME"
log "Run ID: $RUN_ID"
log "Source: $METRICS_PATH"
log "Destination: $REMOTE"


# -----------------------------------------------------------------------------
# Upload
#
# Benchmarks are append-oriented immutable-ish summaries keyed by run ID.
# `hf buckets cp` is used because this operation uploads exactly one file.
# -----------------------------------------------------------------------------

hf buckets cp \
    --token "$HF_TOKEN" \
    "$METRICS_PATH" \
    "$REMOTE"


log "Benchmark upload completed."
