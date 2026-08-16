#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log() { printf '[hf-allocate-id] %s\n' "$*" >&2; }
fail() { printf '[hf-allocate-id] ERROR: %s\n' "$*" >&2; exit 1; }
asr_hf() { cargo run --quiet --locked -p asr-hf -- "$@"; }

COLLECTION="${1:-}"
PREFIX_KEY="${2:-}"

[[ "$COLLECTION" == "candidates" || "$COLLECTION" == "experiments" || "$COLLECTION" == "config" ]] \
  || fail "collection must be 'candidates', 'experiments', or 'config'"
[[ -n "$PREFIX_KEY" ]] || fail "allocation prefix key is required"

if [[ "${HF_ALLOCATOR_INTERNAL:-}" != "1" ]]; then
  exec bash scripts/hf/hf-request-id.sh "$COLLECTION" "$PREFIX_KEY"
fi

[[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v cargo >/dev/null 2>&1 || fail "cargo is unavailable"

PREFIX="$(asr_hf allocation-prefix "$PREFIX_KEY")" \
  || fail "failed to resolve allocation prefix key: $PREFIX_KEY"

BUCKET="${HF_BUCKET#hf://buckets/}"
BUCKET="${BUCKET%/}"
[[ "$BUCKET" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format"

case "$COLLECTION" in
  candidates|experiments)
    REMOTE_ROOT="hf://buckets/${BUCKET}/${COLLECTION}"
    ;;
  config)
    REMOTE_ROOT="hf://buckets/${BUCKET}/config/versions"
    [[ "$PREFIX_KEY" == "config.version" ]] \
      || fail "config allocations must use prefix key 'config.version'"
    ;;
esac

listing="$(mktemp)"
readme="$(mktemp)"
trap 'rm -f "$listing" "$readme" "${listing}.err"' EXIT

if ! hf buckets list --token "$HF_TOKEN" "$REMOTE_ROOT" -R -q >"$listing" 2>"${listing}.err"; then
  if grep -qiE 'not found|does not exist|no files|empty' "${listing}.err"; then
    : >"$listing"
  else
    cat "${listing}.err" >&2
    fail "failed to list ${REMOTE_ROOT}"
  fi
fi

ID="$(asr_hf next-sequence-id --prefix "$PREFIX" --listing "$listing")"
SEQUENCE="${ID##*-}"
CREATED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

asr_hf write-allocation-readme \
  --output "$readme" \
  --allocation-id "$ID" \
  --collection "$COLLECTION" \
  --bucket "$BUCKET" \
  --prefix-key "$PREFIX_KEY" \
  --prefix "$PREFIX" \
  --sequence "$SEQUENCE" \
  --allocated-at "$CREATED_AT" \
  --metadata-json "${HF_ALLOCATION_METADATA_JSON:-{}}"

hf buckets cp --token "$HF_TOKEN" "$readme" "${REMOTE_ROOT}/${ID}/README.md" >/dev/null

log "Allocated ${COLLECTION}/${ID} in ${BUCKET} using ${PREFIX_KEY} -> ${PREFIX}"
printf '%s\n' "$ID"
