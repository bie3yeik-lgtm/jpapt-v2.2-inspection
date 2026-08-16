#!/usr/bin/env bash

set -euo pipefail

# Fetch the selected immutable HF revision-lock configuration.
#
# Remote layout:
#   config/current.json
#   config/versions/config-NNNNNN/
#       reference.json
#       evaluation-schema.json
#       datasets-lock.json
#
# Default selection comes from config/current.json. Set HF_CONFIG_VERSION to a
# config-NNNNNN value to reproduce an older configuration explicitly.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

export PARAKEET_ONNX_REPO_ROOT="$ROOT"

log() { printf '[hf-fetch-revisions] %s\n' "$*"; }
fail() { printf '[hf-fetch-revisions] ERROR: %s\n' "$*" >&2; exit 1; }

require_env() {
    local name="$1"
    [[ -n "${!name:-}" ]] || fail "Required environment variable is not set: $name"
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
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"

HF_BUCKET_ID="${HF_BUCKET#hf://buckets/}"
HF_BUCKET_ID="${HF_BUCKET_ID%/}"
[[ "$HF_BUCKET_ID" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format"
HF_BUCKET_URI="hf://buckets/${HF_BUCKET_ID}"

LOCAL_CONFIG_ROOT="$ROOT/.ci/hf/config"
LOCAL_ROOT="$LOCAL_CONFIG_ROOT/revisions"
mkdir -p "$LOCAL_ROOT"

CURRENT_REMOTE="${HF_BUCKET_URI}/config/current.json"
CURRENT_LOCAL="$LOCAL_CONFIG_ROOT/current.json"
CURRENT_TMP="${CURRENT_LOCAL}.tmp"

log "Bucket: $HF_BUCKET_ID"
log "Fetching configuration pointer: $CURRENT_REMOTE"
rm -f "$CURRENT_TMP"
hf buckets cp --token "$HF_TOKEN" "$CURRENT_REMOTE" "$CURRENT_TMP"
[[ -s "$CURRENT_TMP" ]] || fail "Downloaded config/current.json is empty"
mv -f "$CURRENT_TMP" "$CURRENT_LOCAL"

CURRENT_VERSION="$(
    python - "$CURRENT_LOCAL" <<'PY'
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open("r", encoding="utf-8") as file:
    value = json.load(file)
if not isinstance(value, dict):
    raise SystemExit("config/current.json root must be an object")
if "schema_version" in value and value["schema_version"] != 1:
    raise SystemExit("config/current.json schema_version must equal 1 when present")
version = value.get("config_version")
if not isinstance(version, str) or re.fullmatch(r"config-\d{6}", version) is None:
    raise SystemExit(
        "config/current.json config_version must match config-NNNNNN"
    )
print(version)
PY
)"

CONFIG_VERSION="${HF_CONFIG_VERSION:-$CURRENT_VERSION}"
[[ "$CONFIG_VERSION" =~ ^config-[0-9]{6}$ ]] \
    || fail "HF_CONFIG_VERSION must match config-NNNNNN; got: $CONFIG_VERSION"

SELECTION_SOURCE="current"
if [[ -n "${HF_CONFIG_VERSION:-}" ]]; then
    SELECTION_SOURCE="override"
fi

RESOLVED_LOCAL="$LOCAL_CONFIG_ROOT/resolved.json"
python - "$RESOLVED_LOCAL" "$CONFIG_VERSION" "$CURRENT_VERSION" "$SELECTION_SOURCE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
value = {
    "schema_version": 1,
    "config_version": sys.argv[2],
    "current_version": sys.argv[3],
    "selection_source": sys.argv[4],
}
path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

REMOTE_ROOT="${HF_BUCKET_URI}/config/versions/${CONFIG_VERSION}"
FILES=("reference.json" "evaluation-schema.json" "datasets-lock.json")

log "Current config version: $CURRENT_VERSION"
log "Selected config version: $CONFIG_VERSION ($SELECTION_SOURCE)"
log "Revision source: $REMOTE_ROOT"
log "Destination: $LOCAL_ROOT"

for filename in "${FILES[@]}"; do
    source_uri="${REMOTE_ROOT}/${filename}"
    destination="${LOCAL_ROOT}/${filename}"
    temporary="${destination}.tmp"

    log "Fetching ${source_uri}"
    rm -f "$temporary"
    hf buckets cp --token "$HF_TOKEN" "$source_uri" "$temporary"
    [[ -s "$temporary" ]] || fail "Downloaded revision file is empty: $filename"

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
        f"Expected schema_version=1: {path}; got {value.get('schema_version')!r}"
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
print(f"[hf-fetch-revisions] config version: {bundle.config_version}")
print(f"[hf-fetch-revisions] revision bundle SHA-256: {bundle.sha256}")
PY

log "Revision-lock fetch completed."
