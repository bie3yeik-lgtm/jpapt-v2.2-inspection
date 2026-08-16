#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-push-config-version] %s\n' "$*" >&2; }
fail(){ printf '[hf-push-config-version] ERROR: %s\n' "$*" >&2; exit 1; }

SOURCE="${1:-}"
[[ -d "$SOURCE" ]] || fail "Usage: $0 <directory-containing-reference-evaluation-dataset-jsons>"
[[ $# -eq 1 ]] || fail "runtime profile selection is centralized; do not pass extra positional arguments"
[[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v cargo >/dev/null 2>&1 || fail "cargo is unavailable"
command -v gh >/dev/null 2>&1 || fail "gh CLI is unavailable; central allocation requires GitHub access"

PROFILE_SET="${HF_PROFILE_SET:-${ASR_PROFILE_SET:-}}"
if [[ -z "$PROFILE_SET" && -n "${HF_TARGET_ID:-}" ]]; then
  TARGET_SUMMARY="$(
    cargo run --quiet --locked \
      -p asr-hf \
      -- \
      resolve-target \
      --target "$HF_TARGET_ID"
  )"
  PROFILE_SET="$(printf '%s\n' "$TARGET_SUMMARY" | sed -n 's/^HF_PROFILE_SET=//p')"
fi
[[ -n "$PROFILE_SET" ]] || fail \
  "HF_PROFILE_SET/ASR_PROFILE_SET or HF_TARGET_ID is required to generate runtime.json"

STAGING_PARENT="$(mktemp -d)"
STAGING="$STAGING_PARENT/revisions"
CURRENT="$STAGING_PARENT/current.json"
trap 'rm -rf "$STAGING_PARENT"' EXIT

# Rust owns deterministic config bookkeeping; shell keeps allocation and transport orchestration only.
log "Preparing and validating normalized revision bundle with Rust..."
PREPARE_SUMMARY="$(
  cargo run --quiet --locked \
    -p asr-contracts \
    --bin asr-config-publish \
    -- \
    prepare \
    --repository-root "$ROOT" \
    --source "$SOURCE" \
    --staging "$STAGING" \
    --profile-set "$PROFILE_SET"
)"
BUNDLE_SHA="$(printf '%s\n' "$PREPARE_SUMMARY" | sed -n 's/^bundle_sha256=//p')"
[[ "$BUNDLE_SHA" =~ ^[0-9A-Fa-f]{64}$ ]] || fail \
  "Rust config publisher did not return a valid bundle SHA-256"

BUCKET="${HF_BUCKET#hf://buckets/}"
BUCKET="${BUCKET%/}"
[[ "$BUCKET" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format"
VERSIONS="hf://buckets/${BUCKET}/config/versions"

CONFIG_VERSION="$(
  CANDIDATE_ID= EVALUATION_ID= PROVIDER_ID= \
  bash scripts/hf/hf-request-id.sh config config.version
)"
[[ "$CONFIG_VERSION" =~ ^config-[0-9]{6}$ ]] || fail \
  "central allocator returned an invalid config version: $CONFIG_VERSION"
REMOTE_VERSION="${VERSIONS}/${CONFIG_VERSION}"

log "Publishing immutable configuration: ${REMOTE_VERSION}"
log "Runtime profile set: ${PROFILE_SET}"
hf buckets sync --token "$HF_TOKEN" "$STAGING" "$REMOTE_VERSION" >/dev/null

cargo run --quiet --locked \
  -p asr-contracts \
  --bin asr-config-publish \
  -- \
  write-current \
  --output "$CURRENT" \
  --config-version "$CONFIG_VERSION" \
  --bundle-sha256 "$BUNDLE_SHA" \
  >/dev/null

hf buckets cp --token "$HF_TOKEN" "$CURRENT" "hf://buckets/${BUCKET}/config/current.json" >/dev/null

log "Activated: ${CONFIG_VERSION}"
log "Profile set: ${PROFILE_SET}"
log "Bundle SHA-256: ${BUNDLE_SHA}"
printf '%s\n' "$CONFIG_VERSION"
