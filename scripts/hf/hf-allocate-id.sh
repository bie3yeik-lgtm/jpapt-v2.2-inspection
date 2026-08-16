#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log() { printf '[hf-allocate-id] %s\n' "$*" >&2; }
fail() { printf '[hf-allocate-id] ERROR: %s\n' "$*" >&2; exit 1; }

COLLECTION="${1:-}"
PREFIX="${2:-}"

[[ "$COLLECTION" == "candidates" || "$COLLECTION" == "experiments" ]] \
  || fail "collection must be 'candidates' or 'experiments'"
[[ -n "$PREFIX" ]] || fail "prefix is required"
[[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"

BUCKET="${HF_BUCKET#hf://buckets/}"
BUCKET="${BUCKET%/}"
[[ "$BUCKET" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format"
REMOTE_ROOT="hf://buckets/${BUCKET}/${COLLECTION}"

listing="$(mktemp)"
readme="$(mktemp)"
trap 'rm -f "$listing" "$readme"' EXIT

# A missing/empty collection is equivalent to an empty listing. Other failures
# should still surface, so only tolerate the exact empty-list case produced by
# a collection with no objects.
if ! hf buckets list --token "$HF_TOKEN" "$REMOTE_ROOT" -R -q >"$listing" 2>"${listing}.err"; then
  if grep -qiE 'not found|does not exist|no files|empty' "${listing}.err"; then
    : >"$listing"
  else
    cat "${listing}.err" >&2
    fail "failed to list ${REMOTE_ROOT}"
  fi
fi
rm -f "${listing}.err"

ID="$(python scripts/ci/next-hf-sequence-id.py --prefix "$PREFIX" --listing "$listing")"
SEQUENCE="${ID##*-}"
CREATED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

cat >"$readme" <<EOF
# ${ID}

This directory identifier was allocated automatically from the largest existing
six-digit sequence in \`${COLLECTION}/\` plus one.

- collection: \`${COLLECTION}\`
- prefix: \`${PREFIX}\`
- sequence: \`${SEQUENCE}\`
- allocated_at: \`${CREATED_AT}\`
- target_id: \`${HF_TARGET_ID:-unknown}\`
- github_run_id: \`${GITHUB_RUN_ID:-local}\`

The numeric suffix is machine-managed. Do not manually renumber or reuse it.
The prefix is descriptive only and does not define an independent sequence.
EOF

# Writing README.md makes the logical directory exist in object storage and
# documents/reserves the allocated ID in the Hub UI.
hf buckets cp --token "$HF_TOKEN" "$readme" "${REMOTE_ROOT}/${ID}/README.md"

log "Allocated ${COLLECTION}/${ID}"
printf '%s\n' "$ID"
