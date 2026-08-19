#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log() { printf '[hf-allocate-id] %s\n' "$*" >&2; }
fail() { printf '[hf-allocate-id] ERROR: %s\n' "$*" >&2; exit 1; }
asr_hf() { cargo run --quiet --locked -p asr-hf -- "$@"; }

COLLECTION="${1:-}"

[[ "$COLLECTION" == "candidates" || "$COLLECTION" == "experiments" || "$COLLECTION" == "config" ]] \
  || fail "collection must be 'candidates', 'experiments', or 'config'"
[[ $# -eq 1 ]] || fail "Usage: $0 <candidates|experiments|config>"

if [[ "${HF_ALLOCATOR_INTERNAL:-}" != "1" ]]; then
  exec bash scripts/hf/hf-request-id.sh "$COLLECTION"
fi

[[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v cargo >/dev/null 2>&1 || fail "cargo is unavailable"

BUCKET="${HF_BUCKET#hf://buckets/}"
BUCKET="${BUCKET%/}"
[[ "$BUCKET" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || \
  fail "HF_BUCKET must use canonical namespace/bucket-name format"
namespace="${BUCKET%%/*}"
bucket_name="${BUCKET#*/}"
if [[ "$namespace" == "." || "$namespace" == ".." || "$bucket_name" == "." || "$bucket_name" == ".." ]]; then
  fail "HF_BUCKET must not contain dot path segments"
fi

PREFIX="$(asr_hf allocation-prefix "$COLLECTION")" \
  || fail "failed to derive allocation prefix for collection: $COLLECTION"

case "$COLLECTION" in
  candidates|experiments)
    LIST_PREFIX="$COLLECTION"
    REMOTE_ROOT="hf://buckets/${BUCKET}/${COLLECTION}"
    ;;
  config)
    LIST_PREFIX="config/versions"
    REMOTE_ROOT="hf://buckets/${BUCKET}/config/versions"
    ;;
esac

listing="$(mktemp)"
readme="$(mktemp)"
trap 'rm -f "$listing" "$readme"' EXIT

if ! python scripts/ci/hf-bucket-list-prefix.py \
  --bucket "$BUCKET" \
  --prefix "$LIST_PREFIX" >"$listing"; then
  fail "failed to list ${REMOTE_ROOT}; refusing to allocate from incomplete remote state"
fi

ID="$(asr_hf next-sequence-id --prefix "$PREFIX" --listing "$listing")"
SEQUENCE="${ID##*-}"
CREATED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

asr_hf write-allocation-readme \
  --output "$readme" \
  --allocation-id "$ID" \
  --collection "$COLLECTION" \
  --bucket "$BUCKET" \
  --prefix "$PREFIX" \
  --sequence "$SEQUENCE" \
  --allocated-at "$CREATED_AT" \
  --metadata-json "${HF_ALLOCATION_METADATA_JSON:-{}}"

hf buckets cp --token "$HF_TOKEN" "$readme" "${REMOTE_ROOT}/${ID}/README.md" >/dev/null

log "Allocated ${COLLECTION}/${ID} in ${BUCKET}"
printf '%s\n' "$ID"
