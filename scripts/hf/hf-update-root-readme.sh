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
REMOTE_README="hf://buckets/${BUCKET}/README.md"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
README="$WORK/README.md"

# Preserve any human-written content outside the managed marker block.
if ! hf buckets cp --token "$HF_TOKEN" "$REMOTE_README" "$README" >/dev/null 2>"$WORK/read.err"; then
  printf '# %s\n\n' "$BUCKET" > "$README"
fi

for collection in candidates experiments; do
  remote="hf://buckets/${BUCKET}/${collection}"
  if ! hf buckets list --token "$HF_TOKEN" "$remote" -R -q >"$WORK/${collection}.txt" 2>/dev/null; then
    : >"$WORK/${collection}.txt"
  fi
done
if ! hf buckets list --token "$HF_TOKEN" "hf://buckets/${BUCKET}/config/versions" -R -q >"$WORK/config.txt" 2>/dev/null; then
  : >"$WORK/config.txt"
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
