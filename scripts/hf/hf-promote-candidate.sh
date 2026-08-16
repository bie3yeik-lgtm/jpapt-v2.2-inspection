#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-promote-candidate] %s\n' "$*"; }
fail(){ printf '[hf-promote-candidate] ERROR: %s\n' "$*" >&2; exit 1; }
require_env(){ [[ -n "${!1:-}" ]] || fail "Required environment variable is not set: $1"; }

require_env HF_TOKEN
require_env HF_BUCKET
require_env HF_MODEL_REPO
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"

CANDIDATE_ID="${1:-}"
RUN_DIRECTORY="${2:-}"
[[ -n "$CANDIDATE_ID" && -n "$RUN_DIRECTORY" ]] || fail "Usage: $0 <candidate-id> <run-directory>"
[[ "$CANDIDATE_ID" != */* && "$CANDIDATE_ID" != *".."* ]] || fail "Unsafe candidate ID"

RUN_DIRECTORY="$(python - "$RUN_DIRECTORY" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
[[ -d "$RUN_DIRECTORY" ]] || fail "Run directory does not exist: $RUN_DIRECTORY"
RUN_CONTEXT="$RUN_DIRECTORY/run-context.json"
METRICS="$RUN_DIRECTORY/metrics.json"
[[ -s "$RUN_CONTEXT" && -s "$METRICS" ]] || fail "run-context.json and metrics.json are required"

run_project_python(){
  if command -v uv >/dev/null 2>&1; then uv run python "$@"; else python "$@"; fi
}

readarray -t RUN_VALUES < <(run_project_python - "$RUN_CONTEXT" "$METRICS" "$CANDIDATE_ID" <<'PY'
import json
import os
import sys
from pathlib import Path
from parakeet_onnx.evaluation import validate_benchmark, validate_run_context

run=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
metrics=json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
expected_id=sys.argv[3]
validate_run_context(run)
validate_benchmark(metrics)
if run.get("run_id") != metrics.get("run_id"):
    raise SystemExit("run-context and metrics run IDs differ")
metric_candidate=metrics.get("candidate")
if not isinstance(metric_candidate,dict) or metric_candidate.get("candidate_id") != expected_id:
    raise SystemExit("metrics candidate ID mismatch")
acceptance=metrics.get("acceptance")
if not isinstance(acceptance,dict) or acceptance.get("passed") is not True:
    raise SystemExit(f"candidate is not accepted: {acceptance!r}")
evaluation_id=run.get("evaluation_id")
if evaluation_id != "full" and os.environ.get("HF_PROMOTION_ALLOW_NON_FULL", "0") != "1":
    raise SystemExit(f"promotion requires full evaluation, got {evaluation_id!r}")
metadata=run.get("metadata")
if not isinstance(metadata,dict):
    raise SystemExit("run-context metadata must be an object")
provenance=metadata.get("candidate")
if not isinstance(provenance,dict):
    raise SystemExit("run-context metadata.candidate is required")
if provenance.get("candidate_id") != expected_id:
    raise SystemExit("run-context candidate ID mismatch")
variant=provenance.get("variant")
bundle=provenance.get("bundle_sha256")
if not isinstance(variant,str) or not variant:
    raise SystemExit("run-context candidate variant is required")
if not isinstance(bundle,str) or len(bundle) != 64:
    raise SystemExit("run-context candidate bundle_sha256 is required")
if metric_candidate.get("artifact_sha256") != bundle:
    raise SystemExit("metrics candidate identity must equal run-context candidate bundle SHA")
print(run["run_id"])
print(bundle)
print(variant)
print(run.get("model_id") or "")
print(evaluation_id or "")
print(run.get("provider_id") or "")
print(run.get("revisions", {}).get("bundle_sha256") or "")
PY
)
RUN_ID="${RUN_VALUES[0]}"
EXPECTED_SHA256="${RUN_VALUES[1]}"
RUNTIME_VARIANT="${RUN_VALUES[2]}"
MODEL_ID="${RUN_VALUES[3]}"
EVALUATION_ID="${RUN_VALUES[4]}"
PROVIDER_ID="${RUN_VALUES[5]}"
REVISION_BUNDLE_SHA256="${RUN_VALUES[6]}"

BUCKET="${HF_BUCKET#hf://buckets/}"; BUCKET="${BUCKET%/}"
MODEL_REPO="${HF_MODEL_REPO#hf://models/}"; MODEL_REPO="${MODEL_REPO#hf://}"; MODEL_REPO="${MODEL_REPO%/}"
[[ "$BUCKET" == */* && "$MODEL_REPO" == */* ]] || fail "HF Bucket/Model Repo must use namespace/name format"

STAGING="$ROOT/.ci/promotion"
CANDIDATE_ROOT="$STAGING/candidate"
RELEASE_ROOT="$STAGING/release"
rm -rf "$STAGING"
mkdir -p "$CANDIDATE_ROOT" "$RELEASE_ROOT"
REMOTE="hf://buckets/${BUCKET}/candidates/${CANDIDATE_ID}"
log "Fetching $REMOTE"
hf buckets sync --token "$HF_TOKEN" "$REMOTE" "$CANDIDATE_ROOT"
printf '%s\n' "$CANDIDATE_ID" > "$CANDIDATE_ROOT/.candidate-id"

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
python - "$PROMOTION" "$CANDIDATE_ID" "$RUN_ID" "$MODEL_ID" "$EXPECTED_SHA256" "$RUNTIME_VARIANT" "$REVISION_BUNDLE_SHA256" "$EVALUATION_ID" "$PROVIDER_ID" "$BUCKET" "$MODEL_REPO" <<'PY'
import json,sys
from datetime import datetime,timezone
from pathlib import Path
(
 destination,candidate_id,run_id,model_id,candidate_sha,runtime_variant,
 revision_sha,evaluation_id,provider_id,bucket,model_repo
)=sys.argv[1:]
value={
 "schema_version":3,
 "candidate_id":candidate_id,
 "runtime_variant":runtime_variant,
 "validated_run_id":run_id,
 "model_id":model_id,
 "candidate_sha256":candidate_sha,
 "candidate_identity_kind":"variant_bundle",
 "revision_bundle_sha256":revision_sha or None,
 "evaluation_id":evaluation_id,
 "provider_id":provider_id,
 "promoted_at":datetime.now(timezone.utc).isoformat(),
 "source":{"type":"hf_bucket_candidate","bucket":bucket,"candidate_path":f"candidates/{candidate_id}"},
 "destination":{"type":"hf_model_repo","repo_id":model_repo},
}
Path(destination).write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY

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
