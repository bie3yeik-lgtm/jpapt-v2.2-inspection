#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-request-id] %s\n' "$*" >&2; }
fail(){ printf '[hf-request-id] ERROR: %s\n' "$*" >&2; exit 1; }
asr_hf(){ cargo run --quiet --locked -p asr-hf -- "$@"; }

COLLECTION="${1:-}"
PREFIX_KEY="${2:-}"
[[ "$COLLECTION" == "candidates" || "$COLLECTION" == "experiments" || "$COLLECTION" == "config" ]] \
  || fail "collection must be 'candidates', 'experiments', or 'config'"
[[ -n "$PREFIX_KEY" ]] || fail "allocation prefix key is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI (gh) is required"
command -v cargo >/dev/null 2>&1 || fail "cargo is required for the Rust allocation envelope"

# Prefix semantics are validated by the central allocator through the canonical
# Rust allocation catalog before any sequence number is reserved.
if [[ -z "${GH_TOKEN:-}" && -n "${HF_ALLOCATOR_GITHUB_TOKEN:-}" ]]; then
  export GH_TOKEN="$HF_ALLOCATOR_GITHUB_TOKEN"
fi
[[ -n "${GH_TOKEN:-}" ]] || fail \
  "GH_TOKEN or HF_ALLOCATOR_GITHUB_TOKEN is required to call the central allocator"

ALLOCATOR_REPOSITORY="${HF_ALLOCATOR_REPOSITORY:-bie3yeik-lgtm/jpapt-v2.2-inspection}"
ALLOCATOR_WORKFLOW="${HF_ALLOCATOR_WORKFLOW:-hf-central-allocator.yml}"
ALLOCATOR_REF="${HF_ALLOCATOR_REF:-main}"

REQUEST_ID="$(asr_hf allocation-request-id \
  --source-repository "${GITHUB_REPOSITORY:-local}" \
  --run-id "${GITHUB_RUN_ID:-manual}" \
  --run-attempt "${GITHUB_RUN_ATTEMPT:-0}")"

METADATA_JSON="$(asr_hf allocation-metadata \
  --source-repository "${GITHUB_REPOSITORY:-}" \
  --source-run-id "${GITHUB_RUN_ID:-}" \
  --source-run-attempt "${GITHUB_RUN_ATTEMPT:-}" \
  --target-id "${HF_TARGET_ID:-}" \
  --candidate-id "${CANDIDATE_ID:-}" \
  --evaluation-id "${EVALUATION_ID:-}" \
  --provider-id "${PROVIDER_ID:-}" \
  --runtime-variant "${ASR_RUNTIME_VARIANT:-}")"

log "Dispatching ${COLLECTION}/${PREFIX_KEY} allocation to ${ALLOCATOR_REPOSITORY}"
gh workflow run "$ALLOCATOR_WORKFLOW" \
  --repo "$ALLOCATOR_REPOSITORY" \
  --ref "$ALLOCATOR_REF" \
  -f "request_id=${REQUEST_ID}" \
  -f "hf_bucket=${HF_BUCKET#hf://buckets/}" \
  -f "collection=${COLLECTION}" \
  -f "prefix_key=${PREFIX_KEY}" \
  -f "metadata_json=${METADATA_JSON}"

RUN_ID=""
for _ in $(seq 1 60); do
  RUN_ID="$(gh run list \
    --repo "$ALLOCATOR_REPOSITORY" \
    --workflow "$ALLOCATOR_WORKFLOW" \
    --event workflow_dispatch \
    --limit 100 \
    --json databaseId,displayTitle \
    --jq ".[] | select(.displayTitle == \"HF allocate ${REQUEST_ID}\") | .databaseId" \
    | head -n 1)"
  [[ -n "$RUN_ID" ]] && break
  sleep 2
done
[[ -n "$RUN_ID" ]] || fail "central allocator run was not found for request ${REQUEST_ID}"

gh run watch "$RUN_ID" --repo "$ALLOCATOR_REPOSITORY" --exit-status >/dev/null

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
gh run download "$RUN_ID" \
  --repo "$ALLOCATOR_REPOSITORY" \
  --name "hf-allocation-${REQUEST_ID}" \
  --dir "$TMP" >/dev/null

ID="$(asr_hf allocation-response-id "$TMP/allocation.json")"

log "Allocated ${ID} via run ${RUN_ID}"
printf '%s\n' "$ID"
