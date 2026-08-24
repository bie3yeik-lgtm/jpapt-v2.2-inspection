#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --image <digest-pinned-image> --offer-id <vast-offer-id>" >&2
  exit 2
}

IMAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) IMAGE="${2:?missing image}"; shift 2 ;;
    --offer-id) VAST_OFFER_ID="${2:?missing offer id}"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n "$IMAGE" && -n "${VAST_OFFER_ID:-}" ]] || usage
[[ "$IMAGE" =~ ^ghcr\.io/[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]] || {
  echo 'image must be a digest-pinned GHCR reference' >&2
  exit 2
}
[[ "$VAST_OFFER_ID" =~ ^[0-9]+$ ]] || {
  echo 'VAST_OFFER_ID must be a numeric offer ID from Vast offer inventory' >&2
  exit 2
}

: "${VAST_API_KEY:?VAST_API_KEY is required}"
: "${HF_TOKEN:?HF_TOKEN is required to publish metrics}"
: "${RTF_RUN_ID:?RTF_RUN_ID is required}"
: "${RTF_MODEL_ID:?RTF_MODEL_ID is required}"
: "${RTF_MODEL_REVISION:?RTF_MODEL_REVISION is required}"
: "${RTF_DATASET_ID:?RTF_DATASET_ID is required}"
: "${RTF_DATASET_REVISION:?RTF_DATASET_REVISION is required}"
: "${RTF_FIXTURE_REPO_ID:?RTF_FIXTURE_REPO_ID is required}"
: "${RTF_FIXTURE_REVISION:?RTF_FIXTURE_REVISION is required}"
: "${RTF_GPU:?RTF_GPU is required}"
: "${RTF_BATCH_SIZE:?RTF_BATCH_SIZE is required}"
: "${RTF_LOCAL_RECEIPT:?RTF_LOCAL_RECEIPT is required}"

: "${RTF_VAST_DISK_GB:=100}"
: "${RTF_VAST_CREATE_TIMEOUT_MINUTES:=20}"
: "${RTF_VAST_WAIT_TIMEOUT_MINUTES:=30}"
: "${RTF_VAST_POLL_SECONDS:=15}"
: "${RTF_VAST_SSH_TIMEOUT_SECONDS:=30}"
: "${RTF_VAST_PRICING_TYPE:=on-demand}"
: "${RTF_VAST_BID_PRICE:=}"
: "${RTF_IMAGE_DIGEST:=${IMAGE##*@}}"
: "${RTF_OUTPUT:=/output/metrics.json}"
: "${RTF_CONTENT_OUTPUT:=/output/content.json}"
: "${RTF_RESULT_REPO_ID:=gawohok7/rtf-benchmark-fixtures}"
: "${RTF_RESULT_PATH:=results/${RTF_RUN_ID}/metrics.json}"
: "${RTF_MANIFEST:=/workspace/benchmark-v1.jsonl}"
: "${RTF_RECEIPT:=/output/result-receipt.json}"
: "${RTF_PRECISION:=float16}"
: "${RTF_DECODER:=tdt}"
: "${RTF_REPEAT:=3}"
: "${RTF_INSPECTION_PROFILE:=smoke}"
: "${RTF_FIXTURE_FILENAME:=benchmark-v1.jsonl}"
: "${RTF_FIXTURE_MANIFEST_SHA256:=}"
: "${RTF_DATASET_CONFIGURATION:=default}"
: "${RTF_DATASET_SPLIT:=test}"
: "${RTF_DATASET_SEED:=rtf-benchmark-v1-common-voice-ja}"
: "${RTF_DATASET_COUNT_MIN:=20}"
: "${RTF_DATASET_COUNT_MAX:=50}"
: "${RTF_DATASET_TARGET_TOTAL_SEC:=5400}"
: "${RTF_DATASET_MAX_DURATION_SEC:=600}"
: "${RTF_CUDA_DIAGNOSTICS:=0}"

[[ "$RTF_BATCH_SIZE" =~ ^(1|8|32)$ ]] || { echo 'RTF_BATCH_SIZE must be 1, 8, or 32'; exit 2; }
[[ "$RTF_VAST_DISK_GB" =~ ^[1-9][0-9]*$ ]] || { echo 'RTF_VAST_DISK_GB must be positive'; exit 2; }
[[ "$RTF_VAST_PRICING_TYPE" == on-demand || "$RTF_VAST_PRICING_TYPE" == bid ]] || { echo 'unsupported Vast pricing type'; exit 2; }
if [[ "$RTF_VAST_PRICING_TYPE" == bid ]]; then
  [[ "$RTF_VAST_BID_PRICE" =~ ^[0-9]+(\.[0-9]+)?$ ]] || {
    echo 'RTF_VAST_BID_PRICE is required for bid pricing and must be numeric' >&2
    exit 2
  }
fi

instance_id=""
ssh_key="$HOME/.ssh/rtf-vast-${RTF_RUN_ID}.ed25519"
ssh_url=""
ssh_target=""
ssh_port=""
remote_log="${RTF_VAST_LOG:-vast-job.log}"
mkdir -p "$(dirname "$remote_log")" "$(dirname "$RTF_LOCAL_RECEIPT")"

write_blocked_receipt() {
  local code="$1" message="$2"
  jq -n \
    --arg run_id "$RTF_RUN_ID" --arg job_id "${instance_id:-}" \
    --arg error_code "$code" --arg error_message "$message" \
    '{schema_version:1,run_id:$run_id,status:"blocked",job_id:($job_id | if . == "" then null else . end),result_uri:null,result_sha256:null,metrics_uri:null,metrics_sha256:null,error_code:$error_code,error_message:$error_message}' \
    > "$RTF_LOCAL_RECEIPT"
}

destroy_instance() {
  if [[ -n "$instance_id" ]]; then
    vastai destroy instance "$instance_id" --api-key "$VAST_API_KEY" >/dev/null 2>&1 || \
      echo "::warning::failed to destroy Vast instance $instance_id" >&2
  fi
}
trap destroy_instance EXIT

ssh_run() {
  ssh -i "$ssh_key" -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null -o ConnectTimeout="$RTF_VAST_SSH_TIMEOUT_SECONDS" \
    -p "$ssh_port" "$ssh_target" "$@"
}

ssh_keygen -q -t ed25519 -N '' -f "$ssh_key" -C "rtf-${RTF_RUN_ID}"
chmod 600 "$ssh_key"
vastai create ssh-key "$ssh_key.pub" --api-key "$VAST_API_KEY" >/dev/null

create_args=(
  create instance "$VAST_OFFER_ID" --api-key "$VAST_API_KEY" --raw
  --image "$IMAGE" --disk "$RTF_VAST_DISK_GB" --ssh --direct --cancel-unavail
  --onstart-cmd 'sleep infinity'
)
if [[ "$RTF_VAST_PRICING_TYPE" == bid ]]; then
  create_args+=(--bid_price "$RTF_VAST_BID_PRICE")
fi
if [[ -n "${GH_TOKEN:-}" ]]; then
  # The benchmark image is digest-pinned but may be private GHCR content.
  # Vast requires Docker registry credentials at instance creation time.
  create_args+=(--login "-u ${GITHUB_ACTOR:-github-actions[bot]} -p ${GH_TOKEN} ghcr.io")
fi

create_started="$(date +%s)"
create_json="$(vastai "${create_args[@]}" 2>&1)" || {
  write_blocked_receipt VAST_INSTANCE_CREATE_FAILED "Vast instance creation failed: $create_json"
  printf '%s\n' "$create_json" >&2
  exit 1
}
instance_id="$(jq -er '.new_contract // .id // .instance_id' <<<"$create_json" 2>/dev/null || true)"
[[ "$instance_id" =~ ^[0-9]+$ ]] || {
  write_blocked_receipt VAST_INSTANCE_CREATE_FAILED "Vast create response did not contain new_contract: $create_json"
  exit 1
}
echo "Vast instance created: $instance_id"

deadline=$(( $(date +%s) + RTF_VAST_WAIT_TIMEOUT_MINUTES * 60 ))
status=""
instance_json=""
while (( $(date +%s) < deadline )); do
  instance_json="$(vastai show instance "$instance_id" --api-key "$VAST_API_KEY" --raw 2>&1 || true)"
  status="$(jq -er '(.actual_status // .status // .state // "") | ascii_downcase' <<<"$instance_json" 2>/dev/null || true)"
  echo "Vast instance=$instance_id status=${status:-unknown} elapsed=$(( $(date +%s) - create_started ))s"
  case "$status" in
    running) break ;;
    exited|unknown|offline|error|terminated)
      write_blocked_receipt VAST_INSTANCE_NOT_READY "Vast instance reached terminal state ${status}: $instance_json"
      exit 1
      ;;
  esac
  sleep "$RTF_VAST_POLL_SECONDS"
done
[[ "$status" == running ]] || {
  write_blocked_receipt VAST_INSTANCE_READINESS_TIMEOUT "Vast instance did not reach running state within ${RTF_VAST_WAIT_TIMEOUT_MINUTES} minutes"
  exit 1
}

RTF_GPU_PRICE_PER_HOUR="$(jq -er '(.dph_total // .cost_per_hr // .costPerHr // .dph_base) | tonumber | select(isfinite and . >= 0)' <<<"$instance_json" 2>/dev/null || true)"
[[ -n "$RTF_GPU_PRICE_PER_HOUR" ]] || {
  write_blocked_receipt VAST_GPU_PRICE_UNAVAILABLE 'Vast instance status did not expose a usable hourly GPU price'
  exit 1
}
ssh_url="$(vastai ssh-url "$instance_id" --api-key "$VAST_API_KEY" 2>&1 || true)"
if [[ "$ssh_url" =~ ^ssh://([^@]+)@([^:]+):([0-9]+)$ ]]; then
  ssh_target="${BASH_REMATCH[1]}@${BASH_REMATCH[2]}"
  ssh_port="${BASH_REMATCH[3]}"
else
  write_blocked_receipt VAST_SSH_URL_INVALID "Vast ssh-url returned an unsupported value: $ssh_url"
  exit 1
fi

ssh_deadline=$(( $(date +%s) + RTF_VAST_WAIT_TIMEOUT_MINUTES * 60 ))
until ssh_run true >/dev/null 2>&1; do
  (( $(date +%s) < ssh_deadline )) || {
    write_blocked_receipt VAST_SSH_UNAVAILABLE 'Vast instance was running but SSH did not become ready within the timeout'
    exit 1
  }
  sleep "$RTF_VAST_POLL_SECONDS"
done
RTF_QUEUE_LATENCY_SEC="$(( $(date +%s) - create_started ))"

write_remote_environment() {
  local key value
  for key in RTF_RUN_ID RTF_MANIFEST RTF_OUTPUT RTF_CONTENT_OUTPUT RTF_RECEIPT \
    RTF_MODEL_ID RTF_MODEL_REVISION RTF_DATASET_ID RTF_DATASET_REVISION \
    RTF_DATASET_CONFIGURATION RTF_DATASET_SPLIT RTF_DATASET_SEED RTF_DATASET_COUNT_MIN \
    RTF_DATASET_COUNT_MAX RTF_DATASET_TARGET_TOTAL_SEC RTF_DATASET_MAX_DURATION_SEC \
    RTF_INSPECTION_PROFILE RTF_PROFILE_ID RTF_GPU RTF_BATCH_SIZE RTF_PRECISION RTF_REPEAT \
    RTF_DECODER RTF_QUEUE_LATENCY_SEC RTF_FIXTURE_REPO_ID RTF_FIXTURE_REVISION \
    RTF_FIXTURE_FILENAME RTF_FIXTURE_MANIFEST_SHA256 RTF_CUDA_DIAGNOSTICS \
    RTF_RESULT_REPO_ID RTF_RESULT_PATH RTF_IMAGE_DIGEST RTF_GPU_PRICE_PER_HOUR; do
    value="${!key:-}"
    printf '%s=%q\n' "$key" "$value"
  done
  printf 'RTF_PROVIDER=%q\n' cuda
  printf 'RTF_SERVICE_ID=%q\n' vast
  printf 'RTF_JOB_ID=%q\n' "$instance_id"
  printf 'HF_TOKEN=%q\n' "$HF_TOKEN"
}

write_remote_environment | ssh_run 'cat > /run/rtf-benchmark.env && chmod 600 /run/rtf-benchmark.env'
set +e
{
  printf '%s\n' 'set -a' '. /run/rtf-benchmark.env' 'set +a'
  printf '%s\n' 'exec /opt/rtf-benchmark/entrypoint.sh'
} | ssh_run bash -s 2>&1 | tee "$remote_log"
remote_status="${PIPESTATUS[1]}"
set -e

receipt_line="$(grep '^RTF_RESULT_RECEIPT=' "$remote_log" | tail -n 1 || true)"
if [[ -n "$receipt_line" ]]; then
  printf '%s\n' "${receipt_line#RTF_RESULT_RECEIPT=}" > "$RTF_LOCAL_RECEIPT"
else
  ssh_run cat "$RTF_RECEIPT" > "$RTF_LOCAL_RECEIPT" 2>/dev/null || true
fi
if [[ ! -s "$RTF_LOCAL_RECEIPT" ]]; then
  write_blocked_receipt VAST_EXECUTION_FAILED 'Vast execution did not produce a result receipt'
fi
if [[ -n "${RTF_LOCAL_OUTPUT:-}" ]]; then
  ssh_run cat "$RTF_OUTPUT" > "$RTF_LOCAL_OUTPUT" 2>/dev/null || true
fi
if [[ -n "${RTF_LOCAL_CONTENT:-}" ]]; then
  ssh_run cat "$RTF_CONTENT_OUTPUT" > "$RTF_LOCAL_CONTENT" 2>/dev/null || true
fi

if [[ "$remote_status" -ne 0 ]] && ! jq -e '.status == "completed"' "$RTF_LOCAL_RECEIPT" >/dev/null 2>&1; then
  exit "$remote_status"
fi
exit 0
