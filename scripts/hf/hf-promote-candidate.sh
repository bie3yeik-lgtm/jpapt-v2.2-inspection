#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/hf-identity.sh"

log(){ printf '[hf-promote-candidate] %s\n' "$*"; }
fail(){ printf '[hf-promote-candidate] ERROR: %s\n' "$*" >&2; exit 1; }
require_env(){ [[ -n "${!1:-}" ]] || fail "Required environment variable is not set: $1"; }

require_env HF_TOKEN
require_env HF_BUCKET
require_env HF_MODEL_REPO
BUCKET="$(hf_normalize_bucket_id "$HF_BUCKET")" || \
  fail "HF_BUCKET must use canonical namespace/bucket-name format"
MODEL_REPO="$(hf_normalize_model_repo_id "$HF_MODEL_REPO")" || \
  fail "HF_MODEL_REPO must use canonical namespace/model-name format"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v cargo >/dev/null 2>&1 || fail "cargo is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"

CANDIDATE_ID="${1:-}"
RUN_DIRECTORY_INPUT="${2:-}"
[[ -n "$CANDIDATE_ID" && -n "$RUN_DIRECTORY_INPUT" ]] || fail "Usage: $0 <candidate-id> <run-directory>"
[[ "$CANDIDATE_ID" != */* && "$CANDIDATE_ID" != *".."* ]] || fail "Unsafe candidate ID"

INSPECT_ARGS=(
  inspect
  --run-directory "$RUN_DIRECTORY_INPUT"
  --candidate-id "$CANDIDATE_ID"
)
if [[ "${HF_PROMOTION_ALLOW_NON_FULL:-0}" == "1" ]]; then
  INSPECT_ARGS+=(--allow-non-full)
fi

log "Validating promotion evidence with Rust..."
PROMOTION_SUMMARY="$(
  cargo run --quiet --locked \
    -p asr-contracts \
    --bin asr-promotion \
    -- \
    "${INSPECT_ARGS[@]}"
)"
summary_value(){ printf '%s\n' "$PROMOTION_SUMMARY" | sed -n "s/^$1=//p"; }
RUN_DIRECTORY="$(summary_value run_directory)"
RUN_ID="$(summary_value run_id)"
EXPECTED_SHA256="$(summary_value candidate_sha256)"
RUNTIME_VARIANT="$(summary_value runtime_variant)"
MODEL_ID="$(summary_value model_id)"
EVALUATION_ID="$(summary_value evaluation_id)"
PROVIDER_ID="$(summary_value provider_id)"
REVISION_BUNDLE_SHA256="$(summary_value revision_bundle_sha256)"
[[ -d "$RUN_DIRECTORY" ]] || fail "Rust promotion gate returned invalid run directory"
[[ "$EXPECTED_SHA256" =~ ^[0-9A-Fa-f]{64}$ ]] || fail "Rust promotion gate returned invalid candidate SHA-256"

RUN_CONTEXT="$RUN_DIRECTORY/run-context.json"
METRICS="$RUN_DIRECTORY/metrics.json"
[[ -s "$RUN_CONTEXT" && -s "$METRICS" ]] || fail "run-context.json and metrics.json are required"

run_project_python(){
  if command -v uv >/dev/null 2>&1; then uv run python "$@"; else python "$@"; fi
}

STAGING="$ROOT/.ci/promotion"
CANDIDATE_ROOT="$STAGING/candidate"
RELEASE_ROOT="$STAGING/release"
rm -rf "$STAGING"
mkdir -p "$CANDIDATE_ROOT" "$RELEASE_ROOT"
REMOTE="hf://buckets/${BUCKET}/candidates/${CANDIDATE_ID}"
log "Fetching $REMOTE"
hf buckets sync --token "$HF_TOKEN" "$REMOTE" "$CANDIDATE_ROOT"
printf '%s\n' "$CANDIDATE_ID" > "$CANDIDATE_ROOT/.candidate-id"

# CandidateArtifacts and runtime-contract inspection remain Python-native because they bind
# directly to the current ML/runtime implementation. Deterministic promotion bookkeeping is Rust.
ACTUAL_SHA256="$(run_project_python - "$CANDIDATE_ROOT" "$CANDIDATE_ID" "$RUNTIME_VARIANT" <<'PY'
import sys
from pathlib import Path
from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import validate_candidate_runtime_contract
root,candidate_id,runtime_variant=sys.argv[1:]
candidate=CandidateArtifacts.load(root,variant=runtime_variant,repository_root=Path.cwd())
if candidate.candidate_id != candidate_id:
    raise SystemExit("downloaded candidate identity does not match requested candidate")
validate_candidate_runtime_contract(candidate)
print(candidate.bundle_sha256)
PY
)"
[[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]] || fail "Candidate bundle mismatch: expected=$EXPECTED_SHA256 actual=$ACTUAL_SHA256"

cp -R "$CANDIDATE_ROOT/." "$RELEASE_ROOT/"
rm -f "$RELEASE_ROOT/.candidate-id"
mkdir -p "$RELEASE_ROOT/release"
cp "$RUN_CONTEXT" "$RELEASE_ROOT/release/run-context.json"
cp "$METRICS" "$RELEASE_ROOT/release/metrics.json"
PROMOTION="$RELEASE_ROOT/release/promotion.json"

RECORD_ARGS=(
  write-record
  --output "$PROMOTION"
  --candidate-id "$CANDIDATE_ID"
  --run-id "$RUN_ID"
  --model-id "$MODEL_ID"
  --candidate-sha256 "$EXPECTED_SHA256"
  --runtime-variant "$RUNTIME_VARIANT"
  --evaluation-id "$EVALUATION_ID"
  --provider-id "$PROVIDER_ID"
  --bucket "$BUCKET"
  --model-repo "$MODEL_REPO"
)
if [[ -n "$REVISION_BUNDLE_SHA256" ]]; then
  RECORD_ARGS+=(--revision-bundle-sha256 "$REVISION_BUNDLE_SHA256")
fi
cargo run --quiet --locked \
  -p asr-contracts \
  --bin asr-promotion \
  -- \
  "${RECORD_ARGS[@]}" \
  >/dev/null

if [[ ! -f "$RELEASE_ROOT/README.md" ]]; then
  cat > "$RELEASE_ROOT/README.md" <<EOF
---
library_name: onnxruntime
language:
- ja
pipeline_tag: automatic-speech-recognition
---

# ${MODEL_ID}

Validated ASR ONNX candidate promoted from the development Bucket.

- Candidate: \`${CANDIDATE_ID}\`
- Runtime variant: \`${RUNTIME_VARIANT}\`
- Validated run: \`${RUN_ID}\`
- Candidate bundle SHA-256: \`${EXPECTED_SHA256}\`
- Evaluation: \`${EVALUATION_ID}\`
- Provider: \`${PROVIDER_ID}\`
- Revision bundle: \`${REVISION_BUNDLE_SHA256}\`
EOF
fi

if [[ "${HF_PROMOTION_DRY_RUN:-0}" == "1" ]]; then
  log "Dry run; validated release staging at $RELEASE_ROOT"
  find "$RELEASE_ROOT" -type f -print | sort
  exit 0
fi

MODEL_REPO_PATH="${HF_MODEL_REPO_PATH:-.}"
[[ "$MODEL_REPO_PATH" != /* && "$MODEL_REPO_PATH" != *".."* ]] || fail "Unsafe HF_MODEL_REPO_PATH"
hf upload "$MODEL_REPO" "$RELEASE_ROOT" "$MODEL_REPO_PATH" --token "$HF_TOKEN"
hf buckets cp --token "$HF_TOKEN" "$PROMOTION" "hf://buckets/${BUCKET}/runs/${RUN_ID}/promotion.json"

log "Promotion completed: ${CANDIDATE_ID} ${RUNTIME_VARIANT} ${EXPECTED_SHA256} -> ${MODEL_REPO}/${MODEL_REPO_PATH}"
