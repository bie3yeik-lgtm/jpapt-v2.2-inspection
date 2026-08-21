#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"

repository="${1:?repository owner/name is required}"
run_id="${2:?run_id is required}"
service_id="${3:?service_id is required}"
status="${4:?status is required}"
provider="${5:?provider is required}"
environment="${6:?environment is required}"
inspection_profile="${7:?inspection_profile is required (lough|precise)}"
gpu="${8:?gpu is required}"
batch_size="${9:?batch_size is required}"
job_id="${10:-}"
result_uri="${11:-}"
result_sha256="${12:-}"
metrics_sha256="${13:-}"
metrics_uri="${14:-}"
error_code="${15:-}"
error_message="${16:-}"

case "$service_id" in
  hf-inference-endpoint|hf-jobs|runpod-pod|runpod-serverless) ;;
  *) echo "ERROR: unsupported service_id: $service_id" >&2; exit 2 ;;
esac
case "$status" in
  completed|failed|blocked|not_verified) ;;
  *) echo "ERROR: unsupported status: $status" >&2; exit 2 ;;
esac
case "$provider" in
  cpu|cuda|coreml) ;;
  *) echo "ERROR: unsupported provider: $provider" >&2; exit 2 ;;
esac
case "$environment" in
  linux|windows|macos) ;;
  *) echo "ERROR: unsupported environment: $environment" >&2; exit 2 ;;
esac
case "$inspection_profile" in
  lough|precise) ;;
  *) echo "ERROR: unsupported inspection_profile: $inspection_profile" >&2; exit 2 ;;
esac
[[ "$batch_size" =~ ^(1|8|32)$ ]] || { echo "ERROR: unsupported batch_size: $batch_size" >&2; exit 2; }

body_file="$(mktemp)"
trap 'rm -f "$body_file"' EXIT
jq -n \
  --arg ref "${GITHUB_REF_NAME:-main}" \
  --arg run_id "$run_id" \
  --arg service_id "$service_id" \
  --arg status "$status" \
  --arg provider "$provider" \
  --arg environment "$environment" \
  --arg inspection_profile "$inspection_profile" \
  --arg gpu "$gpu" \
  --arg batch_size "$batch_size" \
  --arg job_id "$job_id" \
  --arg result_uri "$result_uri" \
  --arg result_sha256 "$result_sha256" \
  --arg metrics_uri "$metrics_uri" \
  --arg metrics_sha256 "$metrics_sha256" \
  --arg error_code "$error_code" \
  --arg error_message "$error_message" \
  '{ref:$ref,inputs:{run_id:$run_id,service_id:$service_id,status:$status,provider:$provider,environment:$environment,inspection_profile:$inspection_profile,gpu:$gpu,batch_size:$batch_size,job_id:$job_id,result_uri:$result_uri,result_sha256:$result_sha256,metrics_sha256:$metrics_sha256,metrics_uri:$metrics_uri,error_code:$error_code,error_message:$error_message}}' \
  > "$body_file"

bash scripts/ci/workflow-dispatch-with-retry.sh \
  "$repository" rtf-service-result.yml "$body_file" 3
