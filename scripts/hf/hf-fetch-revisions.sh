#!/usr/bin/env bash

set -euo pipefail

# -----------------------------------------------------------------------------
# Fetch canonical Hugging Face revision-lock documents.
#
# Remote:
#
#   hf://buckets/<HF_BUCKET>/config/revisions/
#       reference.json
#       evaluation-schema.json
#       datasets-lock.json
#
# Local:
#
#   .ci/hf/config/revisions/
#
# The project loader is the authoritative schema/compatibility validator.
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
    printf '[hf-fetch-revisions] %s\n' "$*"
}

fail() {
    printf '[hf-fetch-revisions] ERROR: %s\n' "$*" >&2
    exit 1
}

require_env() {
    local name="$1"

    if [[ -z "${!name:-}" ]]; then
        fail "Required environment variable is not set: $name"
    fi
}

require_command() {
    local command_name="$1"

    if ! command -v "$command_name" >/dev/null 2>&1; then
        fail "Required command is unavailable: $command_name"
    fi
}

normalize_bucket_id() {
    local value="$1"

    value="${value#hf://buckets/}"
    value="${value%/}"

    if [[ "$value" != */* ]]; then
        fail \
            "HF_BUCKET must use namespace/bucket-name format; got: $value"
    fi

    printf '%s\n' "$value"
}

run_project_python() {
    if command -v uv >/dev/null 2>&1; then
        uv run python "$@"
    else
        python "$@"
    fi
}

require_env HF_TOKEN
require_env HF_BUCKET

require_command hf
require_command python

HF_BUCKET_ID="$(normalize_bucket_id "$HF_BUCKET")"
HF_BUCKET_URI="hf://buckets/${HF_BUCKET_ID}"

REMOTE_ROOT="${HF_BUCKET_URI}/config/revisions"
LOCAL_ROOT="$ROOT/.ci/hf/config/revisions"

mkdir -p "$LOCAL_ROOT"

FILES=(
    "reference.json"
    "evaluation-schema.json"
    "datasets-lock.json"
)

log "Bucket: $HF_BUCKET_ID"
log "Destination: $LOCAL_ROOT"

for filename in "${FILES[@]}"; do
    source_uri="${REMOTE_ROOT}/${filename}"
    destination="${LOCAL_ROOT}/${filename}"
    temporary="${destination}.tmp"

    log "Fetching ${source_uri}"
    rm -f "$temporary"

    hf buckets cp \
        --token "$HF_TOKEN" \
        "$source_uri" \
        "$temporary"

    [[ -s "$temporary" ]] \
        || fail "Downloaded revision file is empty: $filename"

    python - "$temporary" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open("r", encoding="utf-8") as file:
    value = json.load(file)

if not isinstance(value, dict):
    raise SystemExit(f"JSON root must be an object: {path}")
if value.get("schema_version") != 1:
    raise SystemExit(
        f"Expected schema_version=1: {path}; "
        f"got {value.get('schema_version')!r}"
    )
PY

    mv -f "$temporary" "$destination"
    log "Fetched: $filename"
done

log "Validating revision bundle with project loader..."

run_project_python - "$LOCAL_ROOT" <<'PY'
import sys

from parakeet_onnx.hf.revisions import load_revision_bundle

bundle = load_revision_bundle(sys.argv[1])
print(
    "[hf-fetch-revisions] "
    f"revision bundle SHA-256: {bundle.sha256}"
)
PY

log "Revision-lock fetch completed."
