#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-push-config-version] %s\n' "$*" >&2; }
fail(){ printf '[hf-push-config-version] ERROR: %s\n' "$*" >&2; exit 1; }

SOURCE="${1:-}"
[[ -d "$SOURCE" ]] || fail "Usage: $0 <directory-containing-reference-evaluation-dataset-jsons>"
[[ $# -eq 1 ]] || fail "runtime profile selection is centralized; do not pass extra positional arguments"
[[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"
command -v gh >/dev/null 2>&1 || fail "gh CLI is unavailable; central allocation requires GitHub access"

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

PROFILE_SET="${HF_PROFILE_SET:-${ASR_PROFILE_SET:-}}"
if [[ -z "$PROFILE_SET" && -n "${HF_TARGET_ID:-}" ]]; then
  PROFILE_SET="$(run_project_python - "$HF_TARGET_ID" <<'PY'
import sys
from pathlib import Path
from parakeet_onnx.hf.targets import load_hf_target_by_id
print(load_hf_target_by_id(sys.argv[1], repository_root=Path.cwd()).profile_set_id)
PY
)"
fi
[[ -n "$PROFILE_SET" ]] || fail \
  "HF_PROFILE_SET/ASR_PROFILE_SET or HF_TARGET_ID is required to generate runtime.json"

STAGING="$(mktemp -d)"
current="$(mktemp)"
trap 'rm -rf "$STAGING"; rm -f "$current"' EXIT
cp "$SOURCE/reference.json" "$STAGING/reference.json"
cp "$SOURCE/evaluation-schema.json" "$STAGING/evaluation-schema.json"
cp "$SOURCE/datasets-lock.json" "$STAGING/datasets-lock.json"

# Normalized config documents must not duplicate decoder declarations. The
# generated runtime.json references the immutable central catalog fingerprint.
run_project_python - "$STAGING" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
for name in ("reference.json","evaluation-schema.json"):
    path=root/name; value=json.loads(path.read_text(encoding="utf-8"))
    if "decoders" in value or "decoder" in value or "decorders" in value:
        raise SystemExit(
            f"{name}: decoder declarations are centralized; remove decoder/decoders fields"
        )
PY
run_project_python scripts/ci/write-runtime-lock.py \
  --profile-set "$PROFILE_SET" \
  --output "$STAGING/runtime.json"

BUNDLE_SHA="$(run_project_python - "$STAGING" <<'PY'
import sys
from parakeet_onnx.hf.revisions import load_revision_bundle
bundle=load_revision_bundle(sys.argv[1])
if bundle.runtime is None:
    raise SystemExit("normalized config requires runtime.json")
print(bundle.sha256)
PY
)"

BUCKET="${HF_BUCKET#hf://buckets/}"
BUCKET="${BUCKET%/}"
[[ "$BUCKET" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format"
VERSIONS="hf://buckets/${BUCKET}/config/versions"

CONFIG_VERSION="$(
  CANDIDATE_ID= EVALUATION_ID= PROVIDER_ID= \
  bash scripts/hf/hf-request-id.sh config config.version
)"
REMOTE_VERSION="${VERSIONS}/${CONFIG_VERSION}"

log "Publishing immutable configuration: ${REMOTE_VERSION}"
log "Runtime profile set: ${PROFILE_SET}"
hf buckets sync --token "$HF_TOKEN" "$STAGING" "$REMOTE_VERSION" >/dev/null

python - "$current" "$CONFIG_VERSION" "$BUNDLE_SHA" <<'PY'
import json,sys
from datetime import datetime,timezone
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
log "Profile set: ${PROFILE_SET}"
log "Bundle SHA-256: ${BUNDLE_SHA}"
printf '%s\n' "$CONFIG_VERSION"
