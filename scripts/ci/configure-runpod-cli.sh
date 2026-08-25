#!/usr/bin/env bash
set -euo pipefail

# Non-interactive RunPod CLI setup for CI and local scripts.
# Repository secret RUNPOD_TOKEN remains canonical; runpodctl reads RUNPOD_API_KEY.
# See https://docs.runpod.io/runpodctl/overview

usage() {
  cat >&2 <<'EOF'
usage: configure-runpod-cli.sh [--doctor] [--doctor-timeout SECONDS]

Exports RUNPOD_API_KEY from RUNPOD_TOKEN for runpodctl. With --doctor, runs
runpodctl doctor --output json and requires healthy=true.
EOF
  exit 2
}

run_doctor=0
doctor_timeout=90

while [[ $# -gt 0 ]]; do
  case "$1" in
    --doctor) run_doctor=1; shift ;;
    --doctor-timeout)
      doctor_timeout="${2:?missing --doctor-timeout value}"
      shift 2
      ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

command -v runpodctl >/dev/null || { echo 'runpodctl is required' >&2; exit 1; }
[[ -n "${RUNPOD_TOKEN:-}" ]] || { echo 'RUNPOD_TOKEN is required' >&2; exit 1; }

export RUNPOD_API_KEY="$RUNPOD_TOKEN"

extract_runpodctl_json() {
  local raw="$1"
  local json=""
  json="$(printf '%s\n' "$raw" | awk '/^\{/ { capture=1 } capture { print }')"
  [[ -n "$json" ]] || return 1
  jq -e . <<<"$json" >/dev/null || return 1
  printf '%s' "$json"
}

if [[ "$run_doctor" -eq 1 ]]; then
  doctor_raw="$(timeout --signal=TERM "${doctor_timeout}s" runpodctl doctor --output json 2>&1)" || {
    echo "RUNPOD_CLI_DOCTOR_TIMEOUT_OR_FAILURE: RunPod CLI doctor did not complete within ${doctor_timeout} seconds" >&2
    exit 124
  }
  while IFS= read -r line; do
    [[ "$line" == \{* ]] && break
    [[ -n "$line" ]] && echo "$line" >&2
  done <<<"$doctor_raw"
  doctor_json="$(extract_runpodctl_json "$doctor_raw")" || {
    echo 'RunPod CLI doctor did not emit parseable JSON' >&2
    printf '%s\n' "$doctor_raw" >&2
    exit 1
  }
  echo "$doctor_json" | jq .
  jq -e '.healthy == true' <<<"$doctor_json" >/dev/null || {
    echo 'RunPod CLI doctor did not report a healthy configuration' >&2
    exit 1
  }
fi
