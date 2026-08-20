#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"

repository="${1:?repository owner/name is required}"
run_id="${2:?run_id is required}"
service_id="${3:?service_id is required}"
status="${4:?status is required}"
provider="${5:?provider is required}"
environment="${6:?environment is required}"
job_id="${7:-}"
result_uri="${8:-}"
result_sha256="${9:-}"
metrics_sha256="${10:-}"
metrics_uri="${11:-}"
error_code="${12:-}"
error_message="${13:-}"

case "$service_id" in
  hf-inference-endpoint|hf-jobs|runpod-pod|runpod-serverless) ;;
  *) echo "ERROR: unsupported service_id: $service_id" >&2; exit 2 ;;
esac
case "$status" in
  completed|failed|blocked|not_verified) ;;
  *) echo "ERROR: unsupported status: $status" >&2; exit 2 ;;
esac
case "$provider" in
  cpu|cuda|directml|coreml) ;;
  *) echo "ERROR: unsupported provider: $provider" >&2; exit 2 ;;
esac
case "$environment" in
  linux|windows|macos) ;;
  *) echo "ERROR: unsupported environment: $environment" >&2; exit 2 ;;
esac

body_file="$(mktemp)"
trap 'rm -f "$body_file"' EXIT
jq -n \
  --arg ref "${GITHUB_REF_NAME:-main}" \
  --arg run_id "$run_id" \
  --arg service_id "$service_id" \
  --arg status "$status" \
  --arg provider "$provider" \
  --arg environment "$environment" \
  --arg job_id "$job_id" \
  --arg result_uri "$result_uri" \
  --arg result_sha256 "$result_sha256" \
  --arg metrics_uri "$metrics_uri" \
  --arg metrics_sha256 "$metrics_sha256" \
  --arg error_code "$error_code" \
  --arg error_message "$error_message" \
  '{ref:$ref,inputs:{run_id:$run_id,service_id:$service_id,status:$status,provider:$provider,environment:$environment,job_id:$job_id,result_uri:$result_uri,result_sha256:$result_sha256,metrics_sha256:$metrics_sha256,metrics_uri:$metrics_uri,error_code:$error_code,error_message:$error_message}}' \
  > "$body_file"

bash scripts/ci/workflow-dispatch-with-retry.sh \
  "$repository" rtf-service-result.yml "$body_file" 3
