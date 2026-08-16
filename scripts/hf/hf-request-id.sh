#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-request-id] %s\n' "$*" >&2; }
fail(){ printf '[hf-request-id] ERROR: %s\n' "$*" >&2; exit 1; }

COLLECTION="${1:-}"
PREFIX="${2:-}"
[[ "$COLLECTION" == "candidates" || "$COLLECTION" == "experiments" || "$COLLECTION" == "config" ]] \
  || fail "collection must be 'candidates', 'experiments', or 'config'"
[[ -n "$PREFIX" ]] || fail "prefix is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI (gh) is required"
command -v python >/dev/null 2>&1 || fail "python is required"

ALLOCATOR_REPOSITORY="${HF_ALLOCATOR_REPOSITORY:-${GITHUB_REPOSITORY:-bie3yeik-lgtm/jpapt-v2.2-inspection}}"
ALLOCATOR_WORKFLOW="${HF_ALLOCATOR_WORKFLOW:-hf-central-allocator.yml}"
ALLOCATOR_REF="${HF_ALLOCATOR_REF:-main}"

REQUEST_ID="$(python - <<'PY'
import os, re, uuid
base = "-".join(filter(None, [
    os.environ.get("GITHUB_REPOSITORY", "local").replace("/", "-"),
    os.environ.get("GITHUB_RUN_ID", "manual"),
    os.environ.get("GITHUB_RUN_ATTEMPT", "0"),
    uuid.uuid4().hex[:12],
]))
print(re.sub(r"[^A-Za-z0-9_.-]", "-", base)[:180])
PY
)"

METADATA_JSON="$(python - <<'PY'
import json, os
keys = {
    "source_repository": "GITHUB_REPOSITORY",
    "source_run_id": "GITHUB_RUN_ID",
    "source_run_attempt": "GITHUB_RUN_ATTEMPT",
    "target_id": "HF_TARGET_ID",
    "candidate_id": "CANDIDATE_ID",
    "evaluation_id": "EVALUATION_ID",
    "provider_id": "PROVIDER_ID",
}
print(json.dumps({k: os.environ.get(v) for k, v in keys.items() if os.environ.get(v)}, separators=(",", ":")))
PY
)"

log "Dispatching ${COLLECTION}/${PREFIX} allocation to ${ALLOCATOR_REPOSITORY}"
gh workflow run "$ALLOCATOR_WORKFLOW" \
  --repo "$ALLOCATOR_REPOSITORY" \
  --ref "$ALLOCATOR_REF" \
  -f "request_id=${REQUEST_ID}" \
  -f "hf_bucket=${HF_BUCKET#hf://buckets/}" \
  -f "collection=${COLLECTION}" \
  -f "prefix=${PREFIX}" \
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

ID="$(python - "$TMP/allocation.json" <<'PY'
import json, sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
allocation_id=value.get("id")
if not isinstance(allocation_id, str) or not allocation_id:
    raise SystemExit("allocation response does not contain a valid id")
print(allocation_id)
PY
)"

log "Allocated ${ID} via run ${RUN_ID}"
printf '%s\n' "$ID"
