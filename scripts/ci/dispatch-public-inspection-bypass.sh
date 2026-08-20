#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"

repository="${1:?public repository owner/name is required}"
request_id="${2:?request_id is required}"
mode="${3:?mode must be plan or execute}"
print_only="${4:-}"

case "$mode" in
  plan) dry_run=true; execute=false ;;
  execute) dry_run=false; execute=true ;;
  *) echo "ERROR: mode must be plan or execute: $mode" >&2; exit 2 ;;
esac

if [[ "$print_only" != "" && "$print_only" != "--print" ]]; then
  echo "ERROR: optional fourth argument must be --print" >&2
  exit 2
fi

body_file="$(mktemp)"
trap 'rm -f "$body_file"' EXIT
jq -n \
  --arg request_id "$request_id" \
  --argjson dry_run "$dry_run" \
  --argjson execute "$execute" \
  '{event_type:"jpapt.candidate-request",client_payload:{request_id:$request_id,source_repository:"largoyo/Premiere-AutoProcess-Plugin",receipt_repository:"largoyo/Premiere-AutoProcess-Plugin",hf_bucket:"gawohok7/tf-v2.2-onnx-dev-bucket",candidate_id:"candidate-000001",package_name:"jpapt-candidate",dataset_source:"bucket",suite:"smoke",executor:"hf_jobs",environment:"linux-cpu",hf_flavor:"cpu-basic",hf_jobs_image:"ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec",dry_run:$dry_run,execute:$execute}}' > "$body_file"

if [[ "$print_only" == "--print" ]]; then
  jq -S . "$body_file"
  exit 0
fi

bash scripts/ci/repository-dispatch-with-retry.sh "$repository" "$body_file" 3
