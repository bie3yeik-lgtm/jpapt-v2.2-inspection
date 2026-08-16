#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-push-candidate] %s\n' "$*"; }
fail(){ printf '[hf-push-candidate] ERROR: %s\n' "$*" >&2; exit 1; }

SOURCE="${1:-}"
[[ -d "$SOURCE" ]] || fail "Usage: $0 <candidate-directory> [prefix]"
[[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"
command -v gh >/dev/null 2>&1 || fail "gh CLI is unavailable; central allocation requires GitHub access"

PREFIX="${2:-${CANDIDATE_PREFIX:-}}"
if [[ -z "$PREFIX" ]]; then
  base="${HF_TARGET_ID:-candidate}"
  base="$(printf '%s' "$base" | tr '[:upper:]_' '[:lower:]-' | sed -E 's/[^a-z0-9.-]+/-/g; s/^-+//; s/-+$//')"
  PREFIX="${base}-candidate"
fi

CANDIDATE_ID="$(CANDIDATE_ID= EVALUATION_ID= PROVIDER_ID= bash scripts/hf/hf-request-id.sh candidates "$PREFIX")"
REMOTE="hf://buckets/${HF_BUCKET#hf://buckets/}/candidates/${CANDIDATE_ID}"

metadata="$SOURCE/metadata.json"
if [[ -f "$metadata" ]]; then
  python - "$metadata" "$CANDIDATE_ID" <<'PY'
import json
import sys
from pathlib import Path
p=Path(sys.argv[1]); candidate_id=sys.argv[2]
value=json.loads(p.read_text(encoding="utf-8"))
if not isinstance(value,dict): raise SystemExit("metadata.json root must be an object")
value["candidate_id"]=candidate_id
p.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY
fi

# The central allocator already created README.md remotely. Sync without
# --delete so the reservation/provenance README remains part of the candidate.
hf buckets sync --token "$HF_TOKEN" "$SOURCE" "$REMOTE"

log "Candidate ID: $CANDIDATE_ID"
log "Published: $REMOTE"
printf '%s\n' "$CANDIDATE_ID"
