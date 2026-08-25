#!/usr/bin/env bash
set -euo pipefail

usage() { echo "usage: $0 --image <digest-pinned-image>" >&2; exit 2; }
IMAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) IMAGE="${2:?missing image}"; shift 2 ;;
    *) usage ;;
  esac
done
[[ "$IMAGE" =~ ^ghcr\.io/[A-Za-z0-9._/-]+@sha256:[0-9a-fA-F]{64}$ ]] || {
  echo 'CPU RunPod benchmark requires a digest-pinned GHCR image' >&2; exit 2;
}
: "${RUNPOD_TOKEN:?RUNPOD_TOKEN is required}"
: "${RTF_RUN_ID:?RTF_RUN_ID is required}"
: "${RTF_MODEL_ID:?RTF_MODEL_ID is required}"
: "${RTF_MODEL_REVISION:?RTF_MODEL_REVISION is required}"
: "${RTF_DATASET_ID:?RTF_DATASET_ID is required}"
: "${RTF_DATASET_REVISION:?RTF_DATASET_REVISION is required}"
: "${RTF_FIXTURE_REPO_ID:?RTF_FIXTURE_REPO_ID is required}"
: "${RTF_FIXTURE_REVISION:?RTF_FIXTURE_REVISION is required}"
: "${RTF_RESULT_REPO_ID:=gawohok7/rtf-benchmark-fixtures}"
: "${RTF_RESULT_PATH:=results/${RTF_RUN_ID}/metrics.json}"
: "${RTF_BATCH_SIZE:=1}"
: "${RTF_CPU_FLAVOR:=cpu3c}"
: "${RTF_LOCAL_OUTPUT:=metrics.json}"
: "${RTF_LOCAL_RECEIPT:=result-receipt.json}"
: "${RTF_LOCAL_CONTENT:=content.json}"
: "${RTF_IMAGE_DIGEST:=${IMAGE##*@}}"
if [[ "$RTF_IMAGE_DIGEST" == *@* ]]; then RTF_IMAGE_DIGEST="${RTF_IMAGE_DIGEST##*@}"; fi
: "${RTF_INSPECTION_PROFILE:=smoke}"
: "${RTF_PROFILE_ID:=${RTF_INSPECTION_PROFILE}}"
: "${RTF_PRECISION:=float32}"
: "${RTF_REPEAT:=3}"
: "${RTF_DECODER:=tdt}"
: "${RTF_OUTPUT:=/output/metrics.json}"
: "${RTF_CONTENT_OUTPUT:=/output/content.json}"
: "${RTF_MANIFEST:=/workspace/benchmark-v1.jsonl}"
: "${RTF_FIXTURE_FILENAME:=benchmark-v1.jsonl}"
: "${RTF_FIXTURE_MANIFEST_SHA256:=}"
: "${RTF_DATASET_CONFIGURATION:=default}"
: "${RTF_DATASET_SPLIT:=test}"
: "${RTF_DATASET_SEED:=rtf-benchmark-v1-common-voice-ja}"
: "${RTF_DATASET_COUNT_MIN:=20}"
: "${RTF_DATASET_COUNT_MAX:=50}"
: "${RTF_DATASET_TARGET_TOTAL_SEC:=5400}"
: "${RTF_DATASET_MAX_DURATION_SEC:=600}"
: "${RTF_RUNPOD_POLL_SECONDS:=15}"
: "${RTF_RUNPOD_WAIT_TIMEOUT_MINUTES:=30}"
: "${RTF_RUNPOD_SSH_CONNECT_TIMEOUT_SECONDS:=30}"
: "${RTF_RUNPOD_LOG:=runpod-cpu-job.log}"

source "$(dirname "${BASH_SOURCE[0]}")/ci/configure-runpod-cli.sh"
name="$RTF_RUN_ID"
pod_id=""
cleanup() { [[ -n "$pod_id" ]] && runpodctl pod delete "$pod_id" >/dev/null 2>&1 || true; }
trap cleanup EXIT

create_json="$(timeout 20m runpodctl pod create --name "$name" --compute-type cpu --image "$IMAGE" --ssh --ports 22/tcp --output json)"
pod_id="$(jq -er '(.id // .podId // .pod_id) // empty' <<<"$create_json")"
[[ -n "$pod_id" ]] || { echo 'RunPod CPU Pod creation returned no pod id' >&2; exit 1; }

deadline=$(( $(date +%s) + RTF_RUNPOD_WAIT_TIMEOUT_MINUTES * 60 ))
ssh_command=""
while [[ "$(date +%s)" -lt "$deadline" ]]; do
  state="$(runpodctl pod get "$pod_id" --output json 2>/dev/null || true)"
  ssh_info="$(runpodctl ssh info "$pod_id" --output json 2>/dev/null || true)"
  ssh_command="$(jq -er '(.sshCommand // .ssh_command) // empty' <<<"$ssh_info" 2>/dev/null || true)"
  if [[ -n "$ssh_command" ]] && timeout "${RTF_RUNPOD_SSH_CONNECT_TIMEOUT_SECONDS}s" bash -c "$ssh_command true" >/dev/null 2>&1; then break; fi
  if jq -e '((.desiredStatus // "") | ascii_upcase) == "EXITED" or ((.desiredStatus // "") | ascii_upcase) == "TERMINATED"' <<<"$state" >/dev/null 2>&1; then
    echo 'RunPod CPU Pod exited before SSH readiness' >&2; exit 1
  fi
  sleep "$RTF_RUNPOD_POLL_SECONDS"
done
[[ -n "$ssh_command" ]] || { echo 'RunPod CPU Pod did not become SSH-ready' >&2; exit 1; }
ssh_command="${ssh_command/ssh /ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=${RTF_RUNPOD_SSH_CONNECT_TIMEOUT_SECONDS} }"
run_ssh() { local command; printf -v command '%q ' "$@"; eval "$ssh_command $command"; }

price="$(runpodctl pod get "$pod_id" --output json | jq -er '(.costPerHr // .cost_per_hr // .adjustedCostPerHr) | tonumber | select(isfinite and . >= 0)' 2>/dev/null || true)"
[[ -n "$price" ]] || price=""
write_env() {
  for key in RTF_RUN_ID RTF_MANIFEST RTF_OUTPUT RTF_CONTENT_OUTPUT RTF_MODEL_ID RTF_MODEL_REVISION RTF_DATASET_ID RTF_DATASET_REVISION RTF_FIXTURE_REPO_ID RTF_FIXTURE_REVISION RTF_RESULT_REPO_ID RTF_RESULT_PATH RTF_IMAGE_DIGEST RTF_INSPECTION_PROFILE RTF_PROFILE_ID RTF_CPU_FLAVOR RTF_BATCH_SIZE RTF_PRECISION RTF_REPEAT RTF_DECODER RTF_FIXTURE_FILENAME RTF_FIXTURE_MANIFEST_SHA256 RTF_DATASET_CONFIGURATION RTF_DATASET_SPLIT RTF_DATASET_SEED RTF_DATASET_COUNT_MIN RTF_DATASET_COUNT_MAX RTF_DATASET_TARGET_TOTAL_SEC RTF_DATASET_MAX_DURATION_SEC; do printf '%s=%q\n' "$key" "${!key:-}"; done
  printf 'RTF_PROVIDER=cpu\nRTF_SERVICE_ID=runpod-pod\nRTF_GPU=%q\n' "$RTF_CPU_FLAVOR"
  printf 'RTF_COMPUTE_PRICE_PER_HOUR=%q\nHF_TOKEN=%q\nRTF_JOB_ID=%q\n' "$price" "${HF_TOKEN:-}" "$pod_id"
}
write_env | run_ssh tee /run/rtf-benchmark.env >/dev/null
run_ssh chmod 600 /run/rtf-benchmark.env
set +e
{ printf '%s\n' 'set -a' '. /run/rtf-benchmark.env' 'set +a' 'exec /opt/rtf-benchmark/entrypoint.sh'; } | run_ssh bash -s 2>&1 | tee "$RTF_RUNPOD_LOG"
remote_status=${PIPESTATUS[1]}
set -e
grep '^RTF_RESULT_RECEIPT=' "$RTF_RUNPOD_LOG" | tail -n 1 | sed 's/^RTF_RESULT_RECEIPT=//' > "$RTF_LOCAL_RECEIPT" || true
run_ssh cat "$RTF_OUTPUT" > "$RTF_LOCAL_OUTPUT" || true
run_ssh cat "$RTF_CONTENT_OUTPUT" > "$RTF_LOCAL_CONTENT" || true
if [[ ! -s "$RTF_LOCAL_RECEIPT" ]]; then
  run_ssh cat /output/result-receipt.json > "$RTF_LOCAL_RECEIPT" || true
fi
[[ -s "$RTF_LOCAL_RECEIPT" ]] || {
  jq -n --arg run_id "$RTF_RUN_ID" --arg job_id "$pod_id" --arg message "RunPod CPU benchmark produced no receipt" \
    '{schema_version:1,run_id:$run_id,status:"blocked",job_id:$job_id,result_uri:null,result_sha256:null,metrics_uri:null,metrics_sha256:null,error_code:"PROVIDER_EXECUTION_FAILED",error_message:$message}' > "$RTF_LOCAL_RECEIPT"
}
exit "$remote_status"
