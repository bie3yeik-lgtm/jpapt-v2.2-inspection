#!/usr/bin/env bash

set -euo pipefail

# -----------------------------------------------------------------------------
# Upload one complete evaluation run to HF Bucket runs/.
#
# Usage:
#
#   scripts/hf/hf-push-run.sh <run-directory>
#
# Example:
#
#   scripts/hf/hf-push-run.sh results/linux-cpu
#
# Required files:
#
#   run-context.json
#   metrics.json
#   samples.jsonl
#
# Remote:
#
#   hf://buckets/<HF_BUCKET>/runs/<run-id>/
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
    printf '[hf-push-run] %s\n' "$*"
}

fail() {
    printf '[hf-push-run] ERROR: %s\n' "$*" >&2
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

command -v python >/dev/null 2>&1 \
    || fail "python is unavailable."

RUN_DIRECTORY="${1:-}"

[[ -n "$RUN_DIRECTORY" ]] \
    || fail \
        "Run directory is required. Usage: $0 <run-directory>"

RUN_DIRECTORY="$(
    python - "$RUN_DIRECTORY" <<'PY'
import sys
from pathlib import Path

print(
    Path(sys.argv[1])
    .expanduser()
    .resolve()
)
PY
)"

[[ -d "$RUN_DIRECTORY" ]] \
    || fail \
        "Run directory does not exist: $RUN_DIRECTORY"

REQUIRED_FILES=(
    "run-context.json"
    "metrics.json"
    "samples.jsonl"
)

for filename in "${REQUIRED_FILES[@]}"; do
    [[ -s "$RUN_DIRECTORY/$filename" ]] \
        || fail \
            "Required run artifact missing or empty: $filename"
done

RUN_ID="$(
    python - "$RUN_DIRECTORY/run-context.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

with path.open("r", encoding="utf-8") as file:
    value = json.load(file)

run_id = value.get("run_id")

if not isinstance(run_id, str) or not run_id:
    raise SystemExit(
        "run-context.json has no valid run_id"
    )

print(run_id)
PY
)"

METRICS_RUN_ID="$(
    python - "$RUN_DIRECTORY/metrics.json" <<'PY'
import json
import sys
from pathlib import Path

with Path(sys.argv[1]).open(
    "r",
    encoding="utf-8",
) as file:
    value = json.load(file)

run_id = value.get("run_id")

if not isinstance(run_id, str) or not run_id:
    raise SystemExit(
        "metrics.json has no valid run_id"
    )

print(run_id)
PY
)"

[[ "$RUN_ID" == "$METRICS_RUN_ID" ]] \
    || fail \
        "run-context.json and metrics.json use different run IDs."

if command -v uv >/dev/null 2>&1; then
    log "Validating output schemas..."

    uv run python - \
        "$RUN_DIRECTORY/run-context.json" \
        "$RUN_DIRECTORY/metrics.json" \
        "$RUN_DIRECTORY/samples.jsonl" \
        <<'PY'
import json
import sys
from pathlib import Path

from parakeet_onnx.evaluation import (
    validate_benchmark,
    validate_run_context,
    validate_sample_result,
)

run_context_path = Path(sys.argv[1])
metrics_path = Path(sys.argv[2])
samples_path = Path(sys.argv[3])

with run_context_path.open(
    "r",
    encoding="utf-8",
) as file:
    validate_run_context(
        json.load(file)
    )

with metrics_path.open(
    "r",
    encoding="utf-8",
) as file:
    validate_benchmark(
        json.load(file)
    )

count = 0

with samples_path.open(
    "r",
    encoding="utf-8",
) as file:
    for line_number, line in enumerate(
        file,
        start=1,
    ):
        line = line.strip()

        if not line:
            continue

        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"samples.jsonl line {line_number}: {exc}"
            ) from exc

        validate_sample_result(
            value
        )

        count += 1

if count == 0:
    raise SystemExit(
        "samples.jsonl contains no sample results"
    )

print(
    f"[hf-push-run] validated {count} sample results"
)
PY
else
    log \
        "uv unavailable; skipped project JSON Schema validation."
fi

HF_BUCKET_ID="$(normalize_bucket_id "$HF_BUCKET")"

REMOTE="hf://buckets/${HF_BUCKET_ID}/runs/${RUN_ID}"

log "Run ID: $RUN_ID"
log "Source: $RUN_DIRECTORY"
log "Destination: $REMOTE"

# Never use --delete here.
#
# A run is append-oriented durable history. Updating explicitly regenerated
# files is allowed, but this wrapper must not remove existing remote data.
hf buckets sync \
    --token "$HF_TOKEN" \
    "$RUN_DIRECTORY" \
    "$REMOTE"

log "Run upload completed."
