#!/usr/bin/env bash
set -euo pipefail

# No-network, no-provider preflight for the local RTF adapter environment.
# This file intentionally does not call hf, runpodctl, Docker, or any API.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/.env"
PROVIDER="all"

usage() {
  cat >&2 <<'EOF'
usage: rtf-local-preflight.sh [--env-file PATH] [--provider hf|runpod|all]

Checks local tools, dotenv keys, pinned fixture files, and digest/identity
shape without submitting an HF Job, creating a RunPod Pod, pulling an image,
or making a network request.
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="${2:?missing env file}"; shift 2 ;;
    --provider) PROVIDER="${2:?missing provider}"; shift 2 ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

case "$PROVIDER" in hf|runpod|all) ;; *) usage ;; esac
[[ -f "$ENV_FILE" ]] || { echo "missing env file: $ENV_FILE" >&2; exit 1; }

failures=()
warnings=()
require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || failures+=("missing command: $command_name")
}
require_key() {
  local key="$1"
  [[ -n "${!key:-}" ]] || failures+=("missing key: $key")
}

# Parse simple dotenv assignments without executing arbitrary shell content.
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || {
    failures+=("unsupported dotenv line (use KEY=value): ${line%%=*}")
    continue
  }
  key="${line%%=*}"
  value="${line#*=}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  export "$key=$value"
done < "$ENV_FILE"

# Keep the GitHub Actions name canonical; RUNPOD_API is accepted only as a
# local dotenv compatibility alias and is never emitted to provider workflows.
if [[ -z "${RUNPOD_TOKEN:-}" && -n "${RUNPOD_API:-}" ]]; then
  export RUNPOD_TOKEN="$RUNPOD_API"
  warnings+=("RUNPOD_API is a local alias; use RUNPOD_TOKEN for canonical scripts")
fi

require_command bash
require_command jq
require_command python3
[[ "$PROVIDER" == hf || "$PROVIDER" == all ]] && require_command hf
[[ "$PROVIDER" == runpod || "$PROVIDER" == all ]] && require_command runpodctl

[[ -s "$ROOT/rtf-scores/benchmark/benchmark-v1.fixture.json" ]] || failures+=("missing fixture pointer")
[[ -s "$ROOT/rtf-scores/benchmark/benchmark-v1.receipt.json" ]] || failures+=("missing fixture receipt")
[[ -s "$ROOT/evaluation/manifests/rtf-benchmark-v1.json" ]] || failures+=("missing manifest lock")

if command -v jq >/dev/null 2>&1; then
  jq -e '.fixture_repo_id and (.fixture_revision | test("^[0-9a-f]{40}$"))' \
    "$ROOT/rtf-scores/benchmark/benchmark-v1.fixture.json" >/dev/null 2>&1 || \
    failures+=("fixture pointer has invalid repository or revision")
  jq -e '.manifest_sha256 | test("^[0-9a-f]{64}$")' \
    "$ROOT/rtf-scores/benchmark/benchmark-v1.receipt.json" >/dev/null 2>&1 || \
    failures+=("fixture receipt has invalid manifest SHA-256")
fi

if [[ -n "${RTF_IMAGE_DIGEST:-}" && ! "$RTF_IMAGE_DIGEST" =~ ^sha256:[0-9a-fA-F]{64}$ ]]; then
  failures+=("RTF_IMAGE_DIGEST must be sha256:<64 hex>")
fi
if [[ -z "${RTF_IMAGE_DIGEST:-}" ]]; then
  warnings+=("RTF_IMAGE_DIGEST is not configured; required for provider launch")
fi
if [[ "$PROVIDER" == hf || "$PROVIDER" == all ]]; then require_key HF_TOKEN; fi
if [[ "$PROVIDER" == runpod || "$PROVIDER" == all ]]; then require_key RUNPOD_TOKEN; fi

echo "RTF local preflight: provider=$PROVIDER env_file=$ENV_FILE"
if command -v hf >/dev/null 2>&1; then echo "hf=$(hf version 2>/dev/null | tail -n 1 || true)"; fi
if command -v runpodctl >/dev/null 2>&1; then echo "runpodctl=$(runpodctl version 2>/dev/null || true)"; fi
if command -v jq >/dev/null 2>&1; then echo "jq=$(jq --version 2>/dev/null || true)"; fi
for warning in "${warnings[@]}"; do echo "WARNING: $warning"; done
if ((${#failures[@]})); then
  for failure in "${failures[@]}"; do echo "FAIL: $failure" >&2; done
  exit 1
fi
echo "PASS: no-network local provider prerequisites are present"
