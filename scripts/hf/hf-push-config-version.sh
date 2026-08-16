#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-push-config-version] %s\n' "$*" >&2; }
fail(){ printf '[hf-push-config-version] ERROR: %s\n' "$*" >&2; exit 1; }

SOURCE="${1:-}"
[[ -d "$SOURCE" ]] || fail "Usage: $0 <directory-containing-revision-jsons>"
[[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"

SOURCE="$(python - "$SOURCE" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"

for file in reference.json evaluation-schema.json datasets-lock.json; do
  [[ -s "$SOURCE/$file" ]] || fail "missing or empty: $SOURCE/$file"
done

run_project_python(){
  if command -v uv >/dev/null 2>&1; then uv run python "$@"; else python "$@"; fi
}

# Validate the exact documents before publishing any remote state.
BUNDLE_SHA="$(run_project_python - "$SOURCE" <<'PY'
import sys
from parakeet_onnx.hf.revisions import load_revision_bundle
bundle=load_revision_bundle(sys.argv[1])
print(bundle.sha256)
PY
)"

BUCKET="${HF_BUCKET#hf://buckets/}"
BUCKET="${BUCKET%/}"
[[ "$BUCKET" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format"
VERSIONS="hf://buckets/${BUCKET}/config/versions"

listing="$(mktemp)"
current="$(mktemp)"
trap 'rm -f "$listing" "$current" "${listing}.err"' EXIT

if ! hf buckets list --token "$HF_TOKEN" "$VERSIONS" -R -q >"$listing" 2>"${listing}.err"; then
  if grep -qiE 'not found|does not exist|no files|empty' "${listing}.err"; then
    : >"$listing"
  else
    cat "${listing}.err" >&2
    fail "failed to list $VERSIONS"
  fi
fi

CONFIG_VERSION="$(python scripts/ci/next-hf-sequence-id.py --prefix config --listing "$listing")"
REMOTE_VERSION="${VERSIONS}/${CONFIG_VERSION}"

log "Publishing immutable configuration: ${REMOTE_VERSION}"
hf buckets sync --token "$HF_TOKEN" "$SOURCE" "$REMOTE_VERSION" >/dev/null

# Only after all three immutable documents are uploaded do we move the mutable
# current pointer. A failed upload therefore never makes current.json point at a
# partial version.
python - "$current" "$CONFIG_VERSION" "$BUNDLE_SHA" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

value={
    "schema_version":1,
    "config_version":sys.argv[2],
    "bundle_sha256":sys.argv[3],
    "updated_at":datetime.now(timezone.utc).isoformat(),
}
Path(sys.argv[1]).write_text(
    json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
    encoding="utf-8",
)
PY

hf buckets cp --token "$HF_TOKEN" "$current" "hf://buckets/${BUCKET}/config/current.json" >/dev/null

log "Activated: ${CONFIG_VERSION}"
log "Bundle SHA-256: ${BUNDLE_SHA}"
printf '%s\n' "$CONFIG_VERSION"
