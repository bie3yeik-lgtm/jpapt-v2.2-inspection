#!/usr/bin/env bash

set -euo pipefail

# -----------------------------------------------------------------------------
# Promote a validated HF Bucket candidate into the Hugging Face Model Repo.
#
# Usage:
#
#   scripts/hf/hf-promote-model.sh \
#       <candidate-id> \
#       <run-directory>
#
# Example:
#
#   scripts/hf/hf-promote-model.sh \
#       ctc-0007 \
#       results/linux-cpu-full
#
# Required environment variables:
#
#   HF_TOKEN
#   HF_BUCKET
#   HF_MODEL_REPO
#
# Expected Bucket layout:
#
#   hf://buckets/<HF_BUCKET>/
#   ├── candidates/
#   │   └── <candidate-id>/
#   │       ├── *.onnx
#   │       ├── metadata.json
#   │       └── ...
#   │
#   └── runs/
#       └── <run-id>/
#           ├── run-context.json
#           ├── metrics.json
#           └── samples.jsonl
#
# Promotion flow:
#
#   validated candidate
#       ↓
#   verify benchmark acceptance
#       ↓
#   verify candidate SHA-256
#       ↓
#   build release staging directory
#       ↓
#   upload to HF Model Repo
#       ↓
#   write promotion metadata
#
# Non-responsibilities:
#
#   - running evaluation
#   - modifying evaluation acceptance
#   - exporting ONNX
#   - automatically promoting a failed candidate
#
# Promotion is intentionally explicit.
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
    pwd
)"

ROOT="$(
    cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1
    pwd
)"

cd "$ROOT"

export PARAKEET_ONNX_REPO_ROOT="$ROOT"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

log() {
    printf '[hf-promote-model] %s\n' "$*"
}

warn() {
    printf '[hf-promote-model] WARNING: %s\n' "$*" >&2
}

fail() {
    printf '[hf-promote-model] ERROR: %s\n' "$*" >&2
    exit 1
}

require_env() {
    local name="$1"

    if [[ -z "${!name:-}" ]]; then
        fail "Required environment variable is not set: $name"
    fi
}

require_command() {
    local name="$1"

    if ! command -v "$name" >/dev/null 2>&1; then
        fail "Required command is unavailable: $name"
    fi
}

normalize_bucket_id() {
    local value="$1"

    value="${value#hf://buckets/}"
    value="${value%/}"

    if [[ "$value" != */* ]]; then
        fail \
            "HF_BUCKET must use namespace/bucket-name format; got: $value"
    fi

    printf '%s\n' "$value"
}

normalize_model_repo_id() {
    local value="$1"

    value="${value#hf://models/}"
    value="${value#hf://}"
    value="${value%/}"

    if [[ "$value" != */* ]]; then
        fail \
            "HF_MODEL_REPO must use namespace/repository format; got: $value"
    fi

    printf '%s\n' "$value"
}

validate_path_component() {
    local name="$1"
    local value="$2"

    [[ -n "$value" ]] \
        || fail "$name must not be empty."

    if [[ "$value" == *"/"* ]] \
        || [[ "$value" == *"\\"* ]] \
        || [[ "$value" == *".."* ]]; then
        fail "Unsafe $name: $value"
    fi
}

sha256_file() {
    python - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])

digest = hashlib.sha256()

with path.open("rb") as file:
    while True:
        chunk = file.read(1024 * 1024)

        if not chunk:
            break

        digest.update(chunk)

print(digest.hexdigest())
PY
}

# -----------------------------------------------------------------------------
# Required environment
# -----------------------------------------------------------------------------

require_env HF_TOKEN
require_env HF_BUCKET
require_env HF_MODEL_REPO

require_command hf
require_command python

HF_BUCKET_ID="$(
    normalize_bucket_id "$HF_BUCKET"
)"

HF_MODEL_REPO_ID="$(
    normalize_model_repo_id "$HF_MODEL_REPO"
)"

# -----------------------------------------------------------------------------
# Arguments
# -----------------------------------------------------------------------------

CANDIDATE_ID="${1:-}"
RUN_DIRECTORY="${2:-}"

[[ -n "$CANDIDATE_ID" ]] \
    || fail \
        "Candidate ID is required. Usage: $0 <candidate-id> <run-directory>"

[[ -n "$RUN_DIRECTORY" ]] \
    || fail \
        "Run directory is required. Usage: $0 <candidate-id> <run-directory>"

validate_path_component \
    "candidate ID" \
    "$CANDIDATE_ID"

RUN_DIRECTORY="$(
    python - "$RUN_DIRECTORY" <<'PY'
import sys
from pathlib import Path

print(
    Path(sys.argv[1])
    .expanduser()
    .resolve()
)
PY
)"

[[ -d "$RUN_DIRECTORY" ]] \
    || fail \
        "Run directory does not exist: $RUN_DIRECTORY"

RUN_CONTEXT="$RUN_DIRECTORY/run-context.json"
METRICS="$RUN_DIRECTORY/metrics.json"

[[ -s "$RUN_CONTEXT" ]] \
    || fail \
        "run-context.json is missing or empty: $RUN_CONTEXT"

[[ -s "$METRICS" ]] \
    || fail \
        "metrics.json is missing or empty: $METRICS"

# -----------------------------------------------------------------------------
# Validate run/benchmark schema
# -----------------------------------------------------------------------------

if command -v uv >/dev/null 2>&1; then
    log "Validating run-context.json and metrics.json..."

    uv run python - \
        "$RUN_CONTEXT" \
        "$METRICS" \
        <<'PY'
import json
import sys
from pathlib import Path

from parakeet_onnx.evaluation import (
    validate_benchmark,
    validate_run_context,
)

run_context_path = Path(sys.argv[1])
metrics_path = Path(sys.argv[2])

with run_context_path.open(
    "r",
    encoding="utf-8",
) as file:
    validate_run_context(
        json.load(file)
    )

with metrics_path.open(
    "r",
    encoding="utf-8",
) as file:
    validate_benchmark(
        json.load(file)
    )
PY
else
    warn \
        "uv is unavailable; project JSON Schema validation was skipped."
fi

# -----------------------------------------------------------------------------
# Read validation identity
# -----------------------------------------------------------------------------

readarray -t RUN_VALUES < <(
    python - \
        "$RUN_CONTEXT" \
        "$METRICS" \
        "$CANDIDATE_ID" \
        <<'PY'
import json
import sys
from pathlib import Path

run_context_path = Path(sys.argv[1])
metrics_path = Path(sys.argv[2])
expected_candidate_id = sys.argv[3]

with run_context_path.open(
    "r",
    encoding="utf-8",
) as file:
    run_context = json.load(file)

with metrics_path.open(
    "r",
    encoding="utf-8",
) as file:
    metrics = json.load(file)

run_id = run_context.get("run_id")
metrics_run_id = metrics.get("run_id")

if not isinstance(run_id, str) or not run_id:
    raise SystemExit(
        "run-context.json has no valid run_id"
    )

if run_id != metrics_run_id:
    raise SystemExit(
        "run-context.json and metrics.json use different run IDs"
    )

candidate = metrics.get(
    "candidate",
    {},
)

candidate_id = candidate.get(
    "candidate_id"
)

if candidate_id != expected_candidate_id:
    raise SystemExit(
        "Candidate ID mismatch: "
        f"argument={expected_candidate_id!r}, "
        f"metrics={candidate_id!r}"
    )

acceptance = metrics.get(
    "acceptance",
    {},
)

passed = acceptance.get(
    "passed"
)

if passed is not True:
    failed_checks = acceptance.get(
        "failed_checks",
        []
    )

    raise SystemExit(
        "Candidate is not eligible for promotion: "
        f"acceptance.passed={passed!r}, "
        f"failed_checks={failed_checks!r}"
    )

artifact = run_context.get(
    "artifact",
    {},
)

artifact_sha256 = artifact.get(
    "sha256"
)

metrics_sha256 = candidate.get(
    "artifact_sha256"
)

if (
    not isinstance(artifact_sha256, str)
    or len(artifact_sha256) != 64
):
    raise SystemExit(
        "run-context.json has no valid artifact.sha256"
    )

if artifact_sha256 != metrics_sha256:
    raise SystemExit(
        "Artifact SHA mismatch between run-context and metrics"
    )

model_id = run_context.get(
    "model_id"
)

evaluation_id = run_context.get(
    "evaluation_id"
)

provider_id = run_context.get(
    "provider_id"
)

revision_bundle = (
    run_context
    .get("revisions", {})
    .get("bundle_sha256")
)

print(run_id)
print(artifact_sha256)
print(model_id or "")
print(evaluation_id or "")
print(provider_id or "")
print(revision_bundle or "")
PY
)

RUN_ID="${RUN_VALUES[0]}"
EXPECTED_ARTIFACT_SHA256="${RUN_VALUES[1]}"
MODEL_ID="${RUN_VALUES[2]}"
EVALUATION_ID="${RUN_VALUES[3]}"
PROVIDER_ID="${RUN_VALUES[4]}"
REVISION_BUNDLE_SHA256="${RUN_VALUES[5]}"

validate_path_component \
    "run ID" \
    "$RUN_ID"

log "Candidate ID: $CANDIDATE_ID"
log "Validated run ID: $RUN_ID"
log "Model: $MODEL_ID"
log "Evaluation: $EVALUATION_ID"
log "Provider: $PROVIDER_ID"
log "Expected artifact SHA-256: $EXPECTED_ARTIFACT_SHA256"

# -----------------------------------------------------------------------------
# Promotion policy
# -----------------------------------------------------------------------------
#
# Promotion requires a full evaluation by default.
#
# Override only when explicitly intended:
#
#   HF_PROMOTION_ALLOW_NON_FULL=1
# -----------------------------------------------------------------------------

if [[ "$EVALUATION_ID" != "full" ]] \
    && [[ "${HF_PROMOTION_ALLOW_NON_FULL:-0}" != "1" ]]; then
    fail \
        "Promotion requires evaluation_id='full'. Current evaluation: $EVALUATION_ID. Set HF_PROMOTION_ALLOW_NON_FULL=1 only for an intentional exception."
fi

# -----------------------------------------------------------------------------
# Fetch candidate from Bucket
# -----------------------------------------------------------------------------

STAGING_ROOT="$ROOT/.ci/promotion"
CANDIDATE_ROOT="$STAGING_ROOT/candidate"
RELEASE_ROOT="$STAGING_ROOT/release"

rm -rf "$STAGING_ROOT"

mkdir -p \
    "$CANDIDATE_ROOT" \
    "$RELEASE_ROOT"

REMOTE_CANDIDATE="hf://buckets/${HF_BUCKET_ID}/candidates/${CANDIDATE_ID}"

log "Fetching candidate from:"
log "  $REMOTE_CANDIDATE"

hf buckets sync \
    --token "$HF_TOKEN" \
    "$REMOTE_CANDIDATE" \
    "$CANDIDATE_ROOT"

if [[ -z "$(find "$CANDIDATE_ROOT" -mindepth 1 -print -quit)" ]]; then
    fail \
        "Candidate directory is empty after download."
fi

ONNX_FILES=()

while IFS= read -r path; do
    ONNX_FILES+=("$path")
done < <(
    find "$CANDIDATE_ROOT" \
        -type f \
        -name '*.onnx' \
        | sort
)

if [[ "${#ONNX_FILES[@]}" -eq 0 ]]; then
    fail \
        "Candidate contains no ONNX files."
fi

log "Candidate ONNX files:"

for path in "${ONNX_FILES[@]}"; do
    log "  ${path#$CANDIDATE_ROOT/}"
done

# -----------------------------------------------------------------------------
# Verify artifact SHA
# -----------------------------------------------------------------------------
#
# Current RunContext identifies one primary deployment artifact.
#
# For a single-ONNX candidate, verify it directly.
#
# For future multi-artifact candidates, candidate metadata should define
# the primary artifact explicitly.
# -----------------------------------------------------------------------------

PRIMARY_ONNX=""

if [[ -f "$CANDIDATE_ROOT/metadata.json" ]]; then
    PRIMARY_RELATIVE="$(
        python - "$CANDIDATE_ROOT/metadata.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

with path.open(
    "r",
    encoding="utf-8",
) as file:
    value = json.load(file)

candidate = value.get(
    "candidate",
    value,
)

primary = (
    candidate.get("primary_artifact")
    or value.get("primary_artifact")
)

if isinstance(primary, str):
    print(primary)
PY
    )"

    if [[ -n "$PRIMARY_RELATIVE" ]]; then
        PRIMARY_ONNX="$CANDIDATE_ROOT/$PRIMARY_RELATIVE"

        [[ -f "$PRIMARY_ONNX" ]] \
            || fail \
                "metadata.json primary_artifact does not exist: $PRIMARY_RELATIVE"
    fi
fi

if [[ -z "$PRIMARY_ONNX" ]]; then
    if [[ "${#ONNX_FILES[@]}" -eq 1 ]]; then
        PRIMARY_ONNX="${ONNX_FILES[0]}"
    else
        fail \
            "Candidate contains multiple ONNX files but metadata.json does not identify primary_artifact."
    fi
fi

ACTUAL_ARTIFACT_SHA256="$(
    sha256_file "$PRIMARY_ONNX"
)"

if [[ "$ACTUAL_ARTIFACT_SHA256" != "$EXPECTED_ARTIFACT_SHA256" ]]; then
    fail \
        "Candidate artifact SHA-256 differs from validated run. expected=$EXPECTED_ARTIFACT_SHA256 actual=$ACTUAL_ARTIFACT_SHA256"
fi

log "Primary artifact verified:"
log "  ${PRIMARY_ONNX#$CANDIDATE_ROOT/}"

# -----------------------------------------------------------------------------
# Build release staging directory
# -----------------------------------------------------------------------------

log "Building release staging directory..."

# Copy candidate payload exactly.
cp -R \
    "$CANDIDATE_ROOT/." \
    "$RELEASE_ROOT/"

# Evaluation provenance is included under release/.
mkdir -p \
    "$RELEASE_ROOT/release"

cp \
    "$RUN_CONTEXT" \
    "$RELEASE_ROOT/release/run-context.json"

cp \
    "$METRICS" \
    "$RELEASE_ROOT/release/metrics.json"

# -----------------------------------------------------------------------------
# Promotion metadata
# -----------------------------------------------------------------------------

PROMOTED_AT="$(
    python - <<'PY'
from datetime import (
    datetime,
    timezone,
)

print(
    datetime.now(
        timezone.utc
    ).isoformat()
)
PY
)"

GIT_COMMIT="$(
    git rev-parse HEAD 2>/dev/null \
        || true
)"

PROMOTION_METADATA="$RELEASE_ROOT/release/promotion.json"

python - \
    "$PROMOTION_METADATA" \
    "$CANDIDATE_ID" \
    "$RUN_ID" \
    "$MODEL_ID" \
    "$EXPECTED_ARTIFACT_SHA256" \
    "$REVISION_BUNDLE_SHA256" \
    "$EVALUATION_ID" \
    "$PROVIDER_ID" \
    "$PROMOTED_AT" \
    "$GIT_COMMIT" \
    "$HF_BUCKET_ID" \
    "$HF_MODEL_REPO_ID" \
    <<'PY'
import json
import sys
from pathlib import Path

(
    destination,
    candidate_id,
    run_id,
    model_id,
    artifact_sha256,
    revision_bundle_sha256,
    evaluation_id,
    provider_id,
    promoted_at,
    git_commit,
    bucket_id,
    model_repo_id,
) = sys.argv[1:]

value = {
    "schema_version": 1,
    "candidate_id": candidate_id,
    "validated_run_id": run_id,
    "model_id": model_id,
    "artifact_sha256": artifact_sha256,
    "revision_bundle_sha256": (
        revision_bundle_sha256
        or None
    ),
    "evaluation_id": evaluation_id,
    "provider_id": provider_id,
    "promoted_at": promoted_at,
    "git_commit": (
        git_commit
        or None
    ),
    "source": {
        "type": "hf_bucket_candidate",
        "bucket": bucket_id,
        "candidate_path": (
            f"candidates/{candidate_id}"
        ),
    },
    "destination": {
        "type": "hf_model_repo",
        "repo_id": model_repo_id,
    },
}

Path(destination).write_text(
    json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

# -----------------------------------------------------------------------------
# Model card safeguard
# -----------------------------------------------------------------------------
#
# Prefer a candidate-provided README.md.
#
# If none exists, create a minimal generated model card so the release does
# not land in the Hub without provenance.
# -----------------------------------------------------------------------------

if [[ ! -f "$RELEASE_ROOT/README.md" ]]; then
    cat > "$RELEASE_ROOT/README.md" <<EOF
---
library_name: onnxruntime
language:
- ja
pipeline_tag: automatic-speech-recognition
---

# ${MODEL_ID}

Validated ONNX deployment artifact promoted from the project's Hugging Face
development Bucket.

## Release identity

- Candidate: \`${CANDIDATE_ID}\`
- Validated run: \`${RUN_ID}\`
- Artifact SHA-256: \`${EXPECTED_ARTIFACT_SHA256}\`
- Evaluation suite: \`${EVALUATION_ID}\`
- Execution Provider used for promotion gate: \`${PROVIDER_ID}\`
- Revision bundle SHA-256: \`${REVISION_BUNDLE_SHA256}\`

Detailed provenance is stored in:

- \`release/run-context.json\`
- \`release/metrics.json\`
- \`release/promotion.json\`

This Model Repository contains validated deployment artifacts. The canonical
upstream/reference model remains recorded in the release metadata.
EOF
fi

# -----------------------------------------------------------------------------
# Dry run
# -----------------------------------------------------------------------------

if [[ "${HF_PROMOTION_DRY_RUN:-0}" == "1" ]]; then
    log "Dry-run enabled. No Model Repo upload will occur."

    log "Release staging contents:"

    find "$RELEASE_ROOT" \
        -type f \
        -print \
        | sort

    exit 0
fi

# -----------------------------------------------------------------------------
# Upload to Model Repo
# -----------------------------------------------------------------------------
#
# Default destination is repository root.
#
# Optional:
#
#   HF_MODEL_REPO_PATH=onnx/ctc
#
# can place the release under a subdirectory.
# -----------------------------------------------------------------------------

MODEL_REPO_PATH="${HF_MODEL_REPO_PATH:-.}"

if [[ "$MODEL_REPO_PATH" == /* ]] \
    || [[ "$MODEL_REPO_PATH" == *".."* ]]; then
    fail \
        "Unsafe HF_MODEL_REPO_PATH: $MODEL_REPO_PATH"
fi

log "Uploading release to Model Repo:"
log "  repo: $HF_MODEL_REPO_ID"
log "  path: $MODEL_REPO_PATH"

# hf upload supports uploading a directory while preserving its structure.
# Existing same-path files are replaced; unrelated repository files remain.
hf upload \
    "$HF_MODEL_REPO_ID" \
    "$RELEASE_ROOT" \
    "$MODEL_REPO_PATH" \
    --token "$HF_TOKEN"

# -----------------------------------------------------------------------------
# Write promotion record back to Bucket
# -----------------------------------------------------------------------------
#
# Keep an immutable promotion-history record separately from the Model Repo.
# -----------------------------------------------------------------------------

PROMOTION_REMOTE="hf://buckets/${HF_BUCKET_ID}/runs/${RUN_ID}/promotion.json"

log "Recording promotion provenance in HF Bucket..."

hf buckets cp \
    --token "$HF_TOKEN" \
    "$PROMOTION_METADATA" \
    "$PROMOTION_REMOTE"

# -----------------------------------------------------------------------------
# Completion
# -----------------------------------------------------------------------------

cat <<EOF

Promotion completed.

Candidate:
  ${CANDIDATE_ID}

Validated run:
  ${RUN_ID}

Artifact SHA-256:
  ${EXPECTED_ARTIFACT_SHA256}

Source:
  hf://buckets/${HF_BUCKET_ID}/candidates/${CANDIDATE_ID}

Destination Model Repo:
  ${HF_MODEL_REPO_ID}

Destination path:
  ${MODEL_REPO_PATH}

Promotion provenance:
  hf://buckets/${HF_BUCKET_ID}/runs/${RUN_ID}/promotion.json

EOF
