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
# runtime.json references the source-controlled ASR catalog/profile set instead
# of duplicating decoder declarations across reference/evaluation documents.
# Legacy three-file configs remain readable when both old documents still carry
# their decoder declarations.

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
    if command -v uv >/dev/null 2>&1; then uv run python "$@"; else python "$@"; fi
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
rm -f "$LOCAL_ROOT/runtime.json"

CURRENT_REMOTE="${HF_BUCKET_URI}/config/current.json"
CURRENT_LOCAL="$LOCAL_CONFIG_ROOT/current.json"
CURRENT_TMP="${CURRENT_LOCAL}.tmp"

log "Bucket: $HF_BUCKET_ID"
log "Fetching configuration pointer: $CURRENT_REMOTE"
rm -f "$CURRENT_TMP"
hf buckets cp --token "$HF_TOKEN" "$CURRENT_REMOTE" "$CURRENT_TMP"
[[ -s "$CURRENT_TMP" ]] || fail "Downloaded config/current.json is empty"
mv -f "$CURRENT_TMP" "$CURRENT_LOCAL"

CURRENT_VERSION="$(python - "$CURRENT_LOCAL" <<'PY'
import json, re, sys
from pathlib import Path
path=Path(sys.argv[1]); value=json.loads(path.read_text(encoding="utf-8"))
if not isinstance(value,dict): raise SystemExit("config/current.json root must be an object")
if value.get("schema_version") != 1: raise SystemExit("config/current.json schema_version must equal 1")
version=value.get("config_version")
if not isinstance(version,str) or re.fullmatch(r"config-\d{6}",version) is None:
    raise SystemExit("config/current.json config_version must match config-NNNNNN")
print(version)
PY
)"

CONFIG_VERSION="${HF_CONFIG_VERSION:-$CURRENT_VERSION}"
[[ "$CONFIG_VERSION" =~ ^config-[0-9]{6}$ ]] || fail "HF_CONFIG_VERSION must match config-NNNNNN; got: $CONFIG_VERSION"
SELECTION_SOURCE="current"
[[ -n "${HF_CONFIG_VERSION:-}" ]] && SELECTION_SOURCE="override"

RESOLVED_LOCAL="$LOCAL_CONFIG_ROOT/resolved.json"
python - "$RESOLVED_LOCAL" "$CONFIG_VERSION" "$CURRENT_VERSION" "$SELECTION_SOURCE" <<'PY'
import json, sys
from pathlib import Path
value={"schema_version":1,"config_version":sys.argv[2],"current_version":sys.argv[3],"selection_source":sys.argv[4]}
Path(sys.argv[1]).write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY

REMOTE_ROOT="${HF_BUCKET_URI}/config/versions/${CONFIG_VERSION}"
REQUIRED_FILES=("reference.json" "evaluation-schema.json" "datasets-lock.json")

log "Current config version: $CURRENT_VERSION"
log "Selected config version: $CONFIG_VERSION ($SELECTION_SOURCE)"
log "Revision source: $REMOTE_ROOT"

fetch_json() {
    local filename="$1"
    local required="$2"
    local source_uri="${REMOTE_ROOT}/${filename}"
    local destination="$LOCAL_ROOT/$filename"
    local temporary="${destination}.tmp"
    rm -f "$temporary"
    if ! hf buckets cp --token "$HF_TOKEN" "$source_uri" "$temporary" >/dev/null 2>&1; then
        rm -f "$temporary"
        [[ "$required" == "1" ]] && fail "Required config document is missing: $filename"
        return 1
    fi
    [[ -s "$temporary" ]] || fail "Downloaded config document is empty: $filename"
    python - "$temporary" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); value=json.loads(p.read_text(encoding="utf-8"))
if not isinstance(value,dict): raise SystemExit(f"JSON root must be an object: {p}")
if value.get("schema_version") != 1: raise SystemExit(f"Expected schema_version=1: {p}")
PY
    mv -f "$temporary" "$destination"
    log "Fetched: $filename"
}

for filename in "${REQUIRED_FILES[@]}"; do fetch_json "$filename" 1; done
if fetch_json "runtime.json" 0; then
    log "Using normalized runtime profile lock."
else
    log "runtime.json not found; treating selected version as legacy config."
fi

log "Validating revision bundle with project loader..."
run_project_python - "$LOCAL_ROOT" <<'PY'
import sys
from parakeet_onnx.hf.revisions import load_revision_bundle
bundle=load_revision_bundle(sys.argv[1])
print(f"[hf-fetch-revisions] config version: {bundle.config_version}")
print(f"[hf-fetch-revisions] revision bundle SHA-256: {bundle.sha256}")
if bundle.runtime is not None:
    print(f"[hf-fetch-revisions] profile set: {bundle.runtime.profile_set_id}")
    print(f"[hf-fetch-revisions] variants: {','.join(bundle.runtime.variants)}")
PY

log "Revision-lock fetch completed."
