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
command -v cargo >/dev/null 2>&1 || fail "cargo is unavailable"
command -v gh >/dev/null 2>&1 || fail "gh CLI is unavailable; central allocation requires GitHub access"

SOURCE="$(cd -- "$SOURCE" >/dev/null 2>&1 && pwd -P)" \
  || fail "failed to resolve candidate source directory"
metadata="$SOURCE/metadata.json"
[[ -s "$metadata" ]] || fail "minimal metadata.json is required before candidate allocation"
[[ ! -e "$SOURCE/.candidate-id" ]] || fail "refusing to republish a materialized candidate containing .candidate-id"

run_project_python(){
  if command -v uv >/dev/null 2>&1; then uv run python "$@"; else python "$@"; fi
}

# CandidateArtifacts and runtime-contract inspection remain Python-native because they bind
# directly to the current ML/runtime implementation. Allocation and sync-plan policy are Rust.
PROFILE_SET="$(run_project_python - "$SOURCE" <<'PY'
import json
import sys
from pathlib import Path
from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract

root=Path(sys.argv[1])
raw=json.loads((root/"metadata.json").read_text(encoding="utf-8"))
profile_set_id=raw.get("profile_set")
variants=raw.get("variants")
if not isinstance(profile_set_id,str) or not profile_set_id:
    raise SystemExit("metadata.json profile_set is required")
if not isinstance(variants,dict) or not variants:
    raise SystemExit("metadata.json variants must be a non-empty object")

runtime_catalog=load_repository_catalog(Path.cwd())
profile_set=runtime_catalog.profile_set(profile_set_id)
unknown=sorted(set(variants)-set(profile_set.variants))
if unknown:
    raise SystemExit(f"candidate defines variants outside profile set: {unknown}")
for variant in variants:
    candidate=CandidateArtifacts.load(root,variant=variant,repository_root=Path.cwd())
    validate_candidate_runtime_contract(candidate)
    print(
        f"validated:{variant}:{candidate.decoder}:{candidate.artifact_contract}:"
        f"{candidate.bundle_sha256}",
        file=sys.stderr,
    )
print(profile_set_id)
PY
)"
PREFIX_KEY="$(cargo run --quiet --locked -p asr-hf -- candidate-prefix-key "$PROFILE_SET")"

CANDIDATE_ID="$(
  CANDIDATE_ID= EVALUATION_ID= PROVIDER_ID= \
  bash scripts/hf/hf-request-id.sh candidates "$PREFIX_KEY"
)"
REMOTE="hf://buckets/${HF_BUCKET#hf://buckets/}/candidates/${CANDIDATE_ID}"
PLAN="$(mktemp -t hf-candidate-plan.XXXXXX.jsonl)"
trap 'rm -f "$PLAN"' EXIT

# Candidate prefixes are semantically immutable. Generate a plan first and
# reject any operation other than a fresh upload. This prevents a recycled ID
# or accidental rerun from silently updating an existing durable candidate.
hf buckets sync \
  --token "$HF_TOKEN" \
  "$SOURCE" \
  "$REMOTE" \
  --plan "$PLAN"

PLAN_SUMMARY="$(
  cargo run --quiet --locked \
    -p asr-hf \
    --bin asr-candidate-plan \
    -- \
    "$PLAN"
)"
UPLOAD_COUNT="$(printf '%s\n' "$PLAN_SUMMARY" | sed -n 's/^upload_count=//p')"
[[ "$UPLOAD_COUNT" =~ ^[1-9][0-9]*$ ]] || fail "Rust candidate plan validator returned an invalid upload count"
log "Validated fresh candidate plan: ${UPLOAD_COUNT} uploads"

hf buckets sync --token "$HF_TOKEN" --apply "$PLAN"

log "Candidate ID: $CANDIDATE_ID"
log "Profile set: $PROFILE_SET"
log "Prefix key: $PREFIX_KEY"
log "Published: $REMOTE"
printf '%s\n' "$CANDIDATE_ID"
