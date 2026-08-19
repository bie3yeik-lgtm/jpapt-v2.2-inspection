#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-update-root-readme] %s\n' "$*" >&2; }
fail(){ printf '[hf-update-root-readme] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${HF_ALLOCATOR_INTERNAL:-}" == "1" ]] || fail "this script may only run inside the central allocator"
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

REMOTE_README="hf://buckets/${BUCKET}/README.md"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
README="$WORK/README.md"

README_EXISTS="$(python scripts/ci/hf-bucket-object-exists.py --bucket "$BUCKET" --path README.md)" || \
  fail "failed to determine whether ${REMOTE_README} exists"
case "$README_EXISTS" in
  true)
    if ! hf buckets cp --token "$HF_TOKEN" "$REMOTE_README" "$README" >/dev/null; then
      fail "existing allocator README could not be downloaded: ${REMOTE_README}"
    fi
    ;;
  false)
    printf '# %s\n\n' "$BUCKET" > "$README"
    ;;
  *)
    fail "unexpected README existence result: $README_EXISTS"
    ;;
esac

if ! python scripts/ci/hf-bucket-list-prefix.py \
  --bucket "$BUCKET" --prefix candidates >"$WORK/candidates.txt"; then
  fail "failed to list candidates; refusing to update allocator README from incomplete state"
fi
if ! python scripts/ci/hf-bucket-list-prefix.py \
  --bucket "$BUCKET" --prefix experiments >"$WORK/experiments.txt"; then
  fail "failed to list experiments; refusing to update allocator README from incomplete state"
fi
if ! python scripts/ci/hf-bucket-list-prefix.py \
  --bucket "$BUCKET" --prefix config/versions >"$WORK/config.txt"; then
  fail "failed to list config versions; refusing to update allocator README from incomplete state"
fi

UPDATED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
cargo run --quiet --locked \
  -p asr-hf \
  --bin asr-allocator-readme \
  -- \
  --readme "$README" \
  --candidates-listing "$WORK/candidates.txt" \
  --experiments-listing "$WORK/experiments.txt" \
  --config-listing "$WORK/config.txt" \
  --last-id "${HF_ALLOCATED_ID:-unknown}" \
  --last-collection "${HF_ALLOCATED_COLLECTION:-unknown}" \
  --updated-at "$UPDATED_AT" \
  >/dev/null

hf buckets cp --token "$HF_TOKEN" "$README" "$REMOTE_README" >/dev/null
log "Updated ${REMOTE_README}"
