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

SOURCE="$(python - "$SOURCE" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
metadata="$SOURCE/metadata.json"
[[ -s "$metadata" ]] || fail "canonical metadata.json is required before candidate allocation"

run_project_python(){
  if command -v uv >/dev/null 2>&1; then uv run python "$@"; else python "$@"; fi
}

# Validate before consuming a durable sequence number. Existing schema-v1
# candidates remain readable, but newly published candidates must be schema-v2.
run_project_python - "$SOURCE" <<'PY'
import json
import sys
from pathlib import Path
from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract
root=Path(sys.argv[1])
raw=json.loads((root/"metadata.json").read_text(encoding="utf-8"))
if raw.get("schema_version") != 2:
    raise SystemExit("new candidate publication requires metadata schema_version=2")
candidate=CandidateArtifacts.load(root)
validate_candidate_runtime_contract(candidate)
print(f"validated candidate contract: {candidate.decoder}/{candidate.artifact_contract}")
PY

PREFIX="${2:-${CANDIDATE_PREFIX:-}}"
if [[ -z "$PREFIX" ]]; then
  base="${HF_TARGET_ID:-candidate}"
  base="$(printf '%s' "$base" | tr '[:upper:]_' '[:lower:]-' | sed -E 's/[^a-z0-9.-]+/-/g; s/^-+//; s/-+$//')"
  PREFIX="${base}-candidate"
fi

CANDIDATE_ID="$(CANDIDATE_ID= EVALUATION_ID= PROVIDER_ID= bash scripts/hf/hf-request-id.sh candidates "$PREFIX")"
REMOTE="hf://buckets/${HF_BUCKET#hf://buckets/}/candidates/${CANDIDATE_ID}"

python - "$metadata" "$CANDIDATE_ID" <<'PY'
import json
import sys
from pathlib import Path
p=Path(sys.argv[1]); candidate_id=sys.argv[2]
value=json.loads(p.read_text(encoding="utf-8"))
if not isinstance(value,dict): raise SystemExit("metadata.json root must be an object")
if value.get("schema_version") != 2: raise SystemExit("metadata.json schema_version must be 2")
value["candidate_id"]=candidate_id
p.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY

# Re-validate after binding the durable ID.
run_project_python - "$SOURCE" <<'PY'
import sys
from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract
candidate=CandidateArtifacts.load(sys.argv[1])
validate_candidate_runtime_contract(candidate)
print(f"publishing candidate {candidate.candidate_id} bundle={candidate.bundle_sha256}")
PY

# The central allocator already created README.md remotely. Sync without
# --delete so the reservation/provenance README remains part of the candidate.
hf buckets sync --token "$HF_TOKEN" "$SOURCE" "$REMOTE"

log "Candidate ID: $CANDIDATE_ID"
log "Published: $REMOTE"
printf '%s\n' "$CANDIDATE_ID"
