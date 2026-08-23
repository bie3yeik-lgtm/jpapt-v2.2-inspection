#!/usr/bin/env bash
set -euo pipefail

# Execute a local RTF command with values from a deliberately small dotenv
# format. GitHub Actions uses repository secrets; provider credentials are
# never printed or copied to a command line. Do not replace this with
# `source .env`.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/.env"

usage() {
  cat >&2 <<'EOF'
usage: rtf-local-env.sh [--env-file PATH] -- COMMAND [ARG ...]

Reads simple KEY=value dotenv assignments and executes COMMAND with only the
RTF/HF/RunPod variables in the allowlist. Values are not echoed.
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="${2:?missing env file}"; shift 2 ;;
    --) shift; break ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

[[ $# -gt 0 ]] || usage
[[ -f "$ENV_FILE" ]] || { echo "missing env file: $ENV_FILE" >&2; exit 1; }

# Do not let credentials inherited from the caller bypass the local allowlist.
unset GITHUB_PAT_TOKEN GITHUB_CLASSIC_TOKEN GITHUB_TOKEN GH_TOKEN CR_PAT

is_allowed_key() {
  case "$1" in
    HF_TOKEN|RUNPOD_TOKEN|RUNPOD_API|RUNPOD_REGISTRY_AUTH_ID|HF_FLAVOR|RUNPOD_GPU_ID|RTF_*) return 0 ;;
    *) return 1 ;;
  esac
}

while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || {
    echo "unsupported dotenv line: ${line%%=*}" >&2
    exit 2
  }
  key="${line%%=*}"
  value="${line#*=}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  if is_allowed_key "$key"; then
    export "$key=$value"
  fi
done < "$ENV_FILE"

if [[ -z "${RUNPOD_TOKEN:-}" && -n "${RUNPOD_API:-}" ]]; then
  export RUNPOD_TOKEN="$RUNPOD_API"
fi

exec "$@"
