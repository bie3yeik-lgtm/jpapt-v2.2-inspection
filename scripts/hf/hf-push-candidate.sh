#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-push-candidate] %s\n' "$*"; }
fail(){ printf '[hf-push-candidate] ERROR: %s\n' "$*" >&2; exit 1; }

SOURCE="${1:-}"
[[ -d "$SOURCE" ]] || fail "Usage: $0 <candidate-directory>"
[[ $# -eq 1 ]] || fail "candidate prefixes are centrally managed; do not pass a manual prefix"
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

# Validate every declared variant before consuming a durable sequence number.
readarray -t META_VALUES < <(run_project_python - "$SOURCE" <<'PY'
import json
import sys
from pathlib import Path
from parakeet_onnx.config.allocation_catalog import load_repository_allocation_catalog
from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract

root=Path(sys.argv[1])
raw=json.loads((root/"metadata.json").read_text(encoding="utf-8"))
if raw.get("schema_version") != 3:
    raise SystemExit("new candidate publication requires metadata schema_version=3")
profile_set_id=raw.get("profile_set")
if not isinstance(profile_set_id,str) or not profile_set_id:
    raise SystemExit("metadata.json profile_set is required")
variants=raw.get("variants")
if not isinstance(variants,dict) or not variants:
    raise SystemExit("metadata.json variants must be a non-empty object")

runtime_catalog=load_repository_catalog(Path.cwd())
profile_set=runtime_catalog.profile_set(profile_set_id)
if set(variants) - set(profile_set.variants):
    raise SystemExit(
        f"candidate defines variants outside profile set: {sorted(set(variants)-set(profile_set.variants))}"
    )
for variant in variants:
    candidate=CandidateArtifacts.load(root,variant=variant,repository_root=Path.cwd())
    validate_candidate_runtime_contract(candidate)
    print(f"validated:{variant}:{candidate.decoder}:{candidate.artifact_contract}",file=sys.stderr)
allocation_catalog=load_repository_allocation_catalog(Path.cwd())
print(profile_set_id)
print(allocation_catalog.candidate_prefix_key(profile_set_id))
PY
)
PROFILE_SET="${META_VALUES[0]}"
PREFIX_KEY="${META_VALUES[1]}"

CANDIDATE_ID="$(
  CANDIDATE_ID= EVALUATION_ID= PROVIDER_ID= \
  bash scripts/hf/hf-request-id.sh candidates "$PREFIX_KEY"
)"
REMOTE="hf://buckets/${HF_BUCKET#hf://buckets/}/candidates/${CANDIDATE_ID}"

python - "$metadata" "$CANDIDATE_ID" <<'PY'
import json
import sys
from pathlib import Path
p=Path(sys.argv[1]); candidate_id=sys.argv[2]
value=json.loads(p.read_text(encoding="utf-8"))
if not isinstance(value,dict): raise SystemExit("metadata.json root must be an object")
if value.get("schema_version") != 3: raise SystemExit("metadata.json schema_version must be 3")
value["candidate_id"]=candidate_id
p.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY

# Re-validate every variant after binding the durable ID.
run_project_python - "$SOURCE" <<'PY'
import json
import sys
from pathlib import Path
from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract
root=Path(sys.argv[1]); raw=json.loads((root/"metadata.json").read_text(encoding="utf-8"))
for variant in raw["variants"]:
    candidate=CandidateArtifacts.load(root,variant=variant,repository_root=Path.cwd())
    validate_candidate_runtime_contract(candidate)
    print(
        f"publishing {candidate.candidate_id} variant={variant} "
        f"bundle={candidate.bundle_sha256}",
        file=sys.stderr,
    )
PY

hf buckets sync --token "$HF_TOKEN" "$SOURCE" "$REMOTE"

log "Candidate ID: $CANDIDATE_ID"
log "Profile set: $PROFILE_SET"
log "Prefix key: $PREFIX_KEY"
log "Published: $REMOTE"
printf '%s\n' "$CANDIDATE_ID"
