#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --provider {hf|runpod} --image <digest-pinned-image>" >&2
  exit 2
}

PROVIDER=""
IMAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider) PROVIDER="${2:?missing provider}"; shift 2 ;;
    --image) IMAGE="${2:?missing image}"; shift 2 ;;
    *) usage ;;
  esac
done
[[ "$PROVIDER" == "hf" || "$PROVIDER" == "runpod" ]] || usage
[[ -n "$IMAGE" ]] || usage

# Local dotenv compatibility only. GitHub Actions keeps RUNPOD_TOKEN as the
# canonical secret name and never receives RUNPOD_API.
if [[ "$PROVIDER" == runpod && -z "${RUNPOD_TOKEN:-}" && -n "${RUNPOD_API:-}" ]]; then
  export RUNPOD_TOKEN="$RUNPOD_API"
fi

: "${RTF_RUN_ID:?RTF_RUN_ID is required}"
: "${RTF_MANIFEST:=/workspace/benchmark-v1.jsonl}"
: "${RTF_MODEL_ID:?RTF_MODEL_ID is required}"
: "${RTF_MODEL_REVISION:?RTF_MODEL_REVISION is required}"
: "${RTF_DATASET_ID:?RTF_DATASET_ID is required}"
: "${RTF_DATASET_REVISION:?RTF_DATASET_REVISION is required}"
: "${RTF_FIXTURE_REPO_ID:?RTF_FIXTURE_REPO_ID is required}"
: "${RTF_FIXTURE_REVISION:?RTF_FIXTURE_REVISION is required}"
: "${RTF_RESULT_REPO_ID:=gawohok7/rtf-benchmark-fixtures}"
: "${RTF_RESULT_PATH:=results/${RTF_RUN_ID}/metrics.json}"
: "${RTF_IMAGE_DIGEST:=${IMAGE##*@}}"
if [[ "$RTF_IMAGE_DIGEST" == *@* ]]; then
  RTF_IMAGE_DIGEST="${RTF_IMAGE_DIGEST##*@}"
fi
[[ "$RTF_IMAGE_DIGEST" =~ ^sha256:[0-9a-fA-F]{64}$ ]] || {
  echo "RTF_IMAGE_DIGEST must be sha256-pinned" >&2
  exit 2
}
: "${RTF_GPU:?RTF_GPU is required}"
: "${RTF_OUTPUT:=/output/metrics.json}"
: "${RTF_CONTENT_OUTPUT:=/output/content.json}"
: "${RTF_BATCH_SIZE:=1}"
: "${RTF_PRECISION:=float16}"
: "${RTF_DECODER:=tdt}"
: "${RTF_SERVICE_ID:=${PROVIDER}-job}"
: "${RTF_INSPECTION_PROFILE:=smoke}"
: "${RTF_PROFILE_ID:=${RTF_INSPECTION_PROFILE}}"
: "${RTF_DATASET_CONFIGURATION:=default}"
: "${RTF_DATASET_SPLIT:=test}"
: "${RTF_DATASET_SEED:=rtf-benchmark-v1-common-voice-ja}"
: "${RTF_DATASET_COUNT_MIN:=20}"
: "${RTF_DATASET_COUNT_MAX:=50}"
: "${RTF_DATASET_TARGET_TOTAL_SEC:=5400}"
: "${RTF_DATASET_MAX_DURATION_SEC:=600}"
: "${RTF_REPEAT:=3}"
: "${RTF_HF_TIMEOUT:=2h}"
: "${RTF_RUNPOD_MAX_HOURS:=24}"
: "${RTF_RUNPOD_CREATE_TIMEOUT_MINUTES:=20}"
: "${RTF_RUNPOD_WAIT_TIMEOUT_MINUTES:=30}"
: "${RTF_RUNPOD_POLL_SECONDS:=15}"
: "${RTF_RUNPOD_SSH_PROBE_TIMEOUT_SECONDS:=10}"
: "${RTF_RUNPOD_SSH_CONNECT_TIMEOUT_SECONDS:=30}"
: "${RTF_RUNPOD_SSH_INFO_WAIT_MINUTES:=5}"
: "${RTF_RUNPOD_HEARTBEAT_SECONDS:=30}"
: "${RTF_RUNPOD_LOG:=runpod-job.log}"
: "${RTF_RUNPOD_CONTAINER_LOG_TAIL:=100}"
: "${RTF_RUNPOD_MIN_CUDA_VERSION:=13.0}"
: "${RTF_RUNPOD_CLOUD_TYPE:=auto}"
: "${RTF_FIXTURE_FILENAME:=benchmark-v1.jsonl}"
: "${RTF_FIXTURE_MANIFEST_SHA256:=}"
: "${RTF_FIXTURE_LOCAL_DIR:=}"
: "${RTF_HF_429_WAIT_SECONDS:=300}"
: "${RTF_HF_429_MAX_ATTEMPTS:=3}"
: "${RTF_LOCAL_PROVIDER_DIAGNOSTICS:=}"
: "${RTF_RUNPOD_REQUIRE_REGISTRY_AUTH:=0}"

decorate_runpod_ssh_command() {
  local command="$1"
  local connect_timeout="$2"
  [[ "$command" == "ssh "* ]] || {
    echo 'RunPod SSH command must start with ssh' >&2
    return 2
  }
  printf '%s\n' "${command/ssh /ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=${connect_timeout} -o ConnectionAttempts=1 }"
}
if [[ "$PROVIDER" == hf ]]; then
  case "$RTF_GPU" in
    t4) HF_FLAVOR="${HF_FLAVOR:-t4-small}" ;;
    l4) HF_FLAVOR="${HF_FLAVOR:-l4x1}" ;;
    *) echo "HF GPU has no Phase 1 flavor mapping: $RTF_GPU" >&2; exit 2 ;;
  esac
fi
if [[ "$PROVIDER" == runpod ]]; then
  case "$RTF_GPU" in
    a5000) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA RTX A5000}" ;;
    a4000) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA RTX A4000}" ;;
    a4500) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA RTX A4500}" ;;
    a40) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA A40}" ;;
    rtx2000-ada) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA RTX 2000 Ada Generation}" ;;
    rtx4000-ada) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA RTX 4000 Ada Generation}" ;;
    l4) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA L4}" ;;
    rtx3090) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA GeForce RTX 3090}" ;;
    rtx4090) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA GeForce RTX 4090}" ;;
    *) echo "RunPod GPU has no Phase 1 GPU ID mapping: $RTF_GPU" >&2; exit 2 ;;
  esac
fi

case "$PROVIDER:$RTF_GPU" in
  hf:t4|hf:l4|runpod:a5000|runpod:a4000|runpod:a4500|runpod:a40|runpod:rtx2000-ada|runpod:rtx4000-ada|runpod:l4|runpod:rtx3090|runpod:rtx4090) ;;
  *) echo "provider/GPU is outside the Phase 1 RTF matrix: $PROVIDER/$RTF_GPU" >&2; exit 2 ;;
esac

case "$PROVIDER" in
  hf)
    command -v hf >/dev/null || { echo "hf CLI is required" >&2; exit 1; }
    # The image entrypoint consumes these variables. Do not print this command:
    # it contains the provider credential when HF_JOB_ENV is configured.
    hf_env=(
      -e "RTF_RUN_ID=$RTF_RUN_ID" -e "RTF_MANIFEST=$RTF_MANIFEST"
      -e "RTF_OUTPUT=$RTF_OUTPUT" -e "RTF_MODEL_ID=$RTF_MODEL_ID"
      -e "RTF_CONTENT_OUTPUT=$RTF_CONTENT_OUTPUT"
      -e "RTF_MODEL_REVISION=$RTF_MODEL_REVISION" -e "RTF_DATASET_ID=$RTF_DATASET_ID"
      -e "RTF_DATASET_REVISION=$RTF_DATASET_REVISION" -e "RTF_GPU=$RTF_GPU"
      -e "RTF_FIXTURE_REPO_ID=$RTF_FIXTURE_REPO_ID" -e "RTF_FIXTURE_REVISION=$RTF_FIXTURE_REVISION"
      -e "RTF_RESULT_REPO_ID=$RTF_RESULT_REPO_ID" -e "RTF_RESULT_PATH=$RTF_RESULT_PATH"
      -e "RTF_IMAGE_DIGEST=$RTF_IMAGE_DIGEST"
      -e "RTF_PRECISION=$RTF_PRECISION"
      -e "RTF_DECODER=$RTF_DECODER" -e "RTF_REPEAT=$RTF_REPEAT"
      -e "RTF_INSPECTION_PROFILE=$RTF_INSPECTION_PROFILE" -e "RTF_PROFILE_ID=$RTF_PROFILE_ID"
      -e "RTF_DATASET_CONFIGURATION=$RTF_DATASET_CONFIGURATION" -e "RTF_DATASET_SPLIT=$RTF_DATASET_SPLIT"
      -e "RTF_DATASET_SEED=$RTF_DATASET_SEED" -e "RTF_DATASET_COUNT_MIN=$RTF_DATASET_COUNT_MIN"
      -e "RTF_DATASET_COUNT_MAX=$RTF_DATASET_COUNT_MAX" -e "RTF_DATASET_TARGET_TOTAL_SEC=$RTF_DATASET_TARGET_TOTAL_SEC"
      -e "RTF_DATASET_MAX_DURATION_SEC=$RTF_DATASET_MAX_DURATION_SEC" -e "RTF_FIXTURE_FILENAME=$RTF_FIXTURE_FILENAME"
      -e "RTF_FIXTURE_MANIFEST_SHA256=$RTF_FIXTURE_MANIFEST_SHA256"
      -e "RTF_HF_429_WAIT_SECONDS=$RTF_HF_429_WAIT_SECONDS" -e "RTF_HF_429_MAX_ATTEMPTS=$RTF_HF_429_MAX_ATTEMPTS"
      -e "RTF_CUDA_DIAGNOSTICS=${RTF_CUDA_DIAGNOSTICS:-0}"
      -e "RTF_ERROR_LOG=/output/benchmark-error.log"
      -e "RTF_PROVIDER=cuda" -e "RTF_SERVICE_ID=hf-jobs"
    )
    [[ -n "${HF_TOKEN:-}" ]] || { echo "HF_TOKEN is required for HF Jobs" >&2; exit 1; }
    hf_log="${RTF_HF_LOG:-hf-job.log}"
    set +e
    hf jobs run --name "$RTF_RUN_ID" --flavor "$HF_FLAVOR" "${hf_env[@]}" \
      --timeout "$RTF_HF_TIMEOUT" \
      --secrets "HF_TOKEN=$HF_TOKEN" "$IMAGE" /opt/rtf-benchmark/entrypoint.sh \
      --batch-size "$RTF_BATCH_SIZE" 2>&1 | tee "$hf_log"
    hf_status=${PIPESTATUS[0]}
    set -e
    receipt_line="$(grep '^RTF_RESULT_RECEIPT=' "$hf_log" | tail -n 1 || true)"
    content_line="$(grep '^RTF_CONTENT_PROBE=' "$hf_log" | tail -n 1 || true)"
    if [[ -n "$content_line" ]]; then
      printf '%s\n' "${content_line#RTF_CONTENT_PROBE=}" > "${RTF_LOCAL_CONTENT:-content.json}"
    fi
    if [[ -z "$receipt_line" ]]; then
      job_id="$(grep -Eo 'Job [0-9a-f]{24}' "$hf_log" | tail -n 1 | awk '{print $2}' || true)"
      failure_code="PROVIDER_EXECUTION_FAILED"
      failure_message="HF Job did not emit RTF_RESULT_RECEIPT"
      if grep -Eqi 'illegal memory access|cudaErrorIllegalAddress' "$hf_log"; then
        failure_code="PROVIDER_CUDA_ILLEGAL_ACCESS"
        failure_message="HF Job terminated with a CUDA illegal memory access"
      elif grep -Eqi 'driver .*too old|CUDA driver version is insufficient|nvidia driver on your system is too old' "$hf_log"; then
        failure_code="PROVIDER_CUDA_DRIVER_INCOMPATIBLE"
        failure_message="HF Job image CUDA runtime is incompatible with the provider NVIDIA driver"
      elif grep -Eqi 'out of memory|CUDA OOM|cuda out of memory' "$hf_log"; then
        failure_code="PROVIDER_CUDA_OOM"
        failure_message="HF Job terminated with CUDA out of memory"
      fi
      mkdir -p "$(dirname "${RTF_LOCAL_RECEIPT:-result-receipt.json}")"
      jq -n \
        --arg run_id "$RTF_RUN_ID" --arg job_id "$job_id" --arg error_code "$failure_code" \
        --arg error_message "$failure_message" --arg model_id "$RTF_MODEL_ID" \
        --arg model_revision "$RTF_MODEL_REVISION" --arg dataset_id "$RTF_DATASET_ID" \
        --arg dataset_revision "$RTF_DATASET_REVISION" --arg image_digest "$RTF_IMAGE_DIGEST" \
        --arg fixture_repo_id "$RTF_FIXTURE_REPO_ID" --arg fixture_revision "$RTF_FIXTURE_REVISION" \
        --arg manifest_sha256 "$RTF_FIXTURE_MANIFEST_SHA256" --arg gpu "$RTF_GPU" \
        --arg profile "$RTF_INSPECTION_PROFILE" --arg batch_size "$RTF_BATCH_SIZE" \
        '{schema_version:1,run_id:$run_id,status:"blocked",job_id:($job_id | if length == 0 then null else . end),result_uri:null,result_sha256:null,metrics_uri:null,metrics_sha256:null,error_code:$error_code,error_message:$error_message,model_id:$model_id,model_revision:$model_revision,dataset_id:$dataset_id,dataset_revision:$dataset_revision,image_digest:$image_digest,fixture_repo_id:$fixture_repo_id,fixture_revision:$fixture_revision,manifest_sha256:$manifest_sha256,provider:"cuda",environment:"linux",service_id:"hf-jobs",gpu:$gpu,inspection_profile:$profile,batch_size:($batch_size|tonumber)}' \
        > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
      echo "HF Job failure receipt: $failure_code" >&2
      [[ "$hf_status" -ne 0 ]] && exit "$hf_status"
      exit 1
    fi
    printf '%s\n' "${receipt_line#RTF_RESULT_RECEIPT=}" > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
    if jq -e '.status == "completed"' "${RTF_LOCAL_RECEIPT:-result-receipt.json}" >/dev/null 2>&1; then
      metadata_script="scripts/ci/enrich_hf_job_metrics.py"
      [[ -f "$metadata_script" ]] || { echo "HF Job metadata collector is missing: $metadata_script" >&2; exit 2; }
      if ! python "$metadata_script" --receipt "${RTF_LOCAL_RECEIPT:-result-receipt.json}" \
        --namespace "${HF_JOB_NAMESPACE:-gawohok7}"; then
        jq '.status = "blocked" | .error_code = "HF_JOB_METADATA_UNAVAILABLE" | .error_message = "HF Job billing metadata could not be collected; metrics were not accepted for ranking"' \
          "${RTF_LOCAL_RECEIPT:-result-receipt.json}" > "${RTF_LOCAL_RECEIPT:-result-receipt.json}.tmp"
        mv "${RTF_LOCAL_RECEIPT:-result-receipt.json}.tmp" "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
        exit 1
      fi
    fi
    [[ "$hf_status" -eq 0 ]] || exit "$hf_status"
    ;;
  runpod)
    command -v runpodctl >/dev/null || { echo "runpodctl is required" >&2; exit 1; }
    [[ -n "${RUNPOD_TOKEN:-}" ]] || { echo 'RUNPOD_TOKEN is required' >&2; exit 1; }
    export RUNPOD_API_KEY="$RUNPOD_TOKEN"
    if [[ "$RTF_RUNPOD_REQUIRE_REGISTRY_AUTH" == 1 && -z "${RUNPOD_REGISTRY_AUTH_ID:-}" ]]; then
      echo 'RUNPOD_REGISTRY_AUTH_ID is required for the private GHCR image' >&2
      exit 2
    fi
    pod_id=""
    runpod_container_log_pid=""
    runpod_watchdog_pid=""
    runpod_watchdog_failure_file=""
    pod_create_failed=0
    delete_named_pods() {
      local candidate_ids candidate_id
      candidate_ids="$(runpodctl pod list --all --name "$RTF_RUN_ID" --output json 2>/dev/null \
        | jq -r '.[] | (.id // .podId // .pod_id)' 2>/dev/null || true)"
      while IFS= read -r candidate_id; do
        [[ -n "$candidate_id" ]] || continue
        echo "Deleting RunPod Pod $candidate_id found after create failure" >&2
        runpodctl pod delete "$candidate_id" >/dev/null || \
          echo "::error::failed to delete RunPod Pod $candidate_id" >&2
      done <<< "$candidate_ids"
    }
    delete_pod() {
      if [[ -n "$pod_id" ]]; then
        echo "Deleting RunPod Pod $pod_id" >&2
        if runpodctl pod delete "$pod_id" >/dev/null; then
          pod_id=""
        else
          echo "::error::failed to delete RunPod Pod $pod_id" >&2
          return 1
        fi
      fi
    }
    log_runpod_response() {
      local label="$1"
      local response="${2:-}"
      response="$(tr '\r\n' '  ' <<<"$response" | cut -c1-2000)"
      if [[ -n "$response" ]]; then
        echo "RunPod $label response: $response" >&2
      else
        echo "RunPod $label response: <empty>" >&2
      fi
    }
    cleanup_runpod() {
      stop_runpod_pod_watchdog || true
      stop_runpod_container_logs || true
      delete_pod || true
      if [[ "$pod_create_failed" -eq 1 ]]; then
        delete_named_pods
      fi
    }
    start_runpod_container_logs() {
      local log_help
      if ! log_help="$(runpodctl pod logs --help 2>&1)" ||
        ! grep -F 'pod logs <pod-id>' <<<"$log_help" >/dev/null; then
        echo 'RunPod container log streaming is unavailable in this runpodctl version' >&2
        return 0
      fi
      [[ -z "$runpod_container_log_pid" ]] || return 0
      echo "::group::RunPod container logs ($pod_id)"
      (
        runpodctl pod logs "$pod_id" \
          --source container \
          --tail "$RTF_RUNPOD_CONTAINER_LOG_TAIL" \
          --follow 2>&1 |
          while IFS= read -r line; do
            printf 'RunPod container log: %s\n' "$line"
          done
      ) &
      runpod_container_log_pid=$!
    }
    stop_runpod_container_logs() {
      [[ -n "$runpod_container_log_pid" ]] || return 0
      kill "$runpod_container_log_pid" 2>/dev/null || true
      wait "$runpod_container_log_pid" 2>/dev/null || true
      runpod_container_log_pid=""
      echo '::endgroup::'
    }
    start_runpod_pod_watchdog() {
      [[ -n "$pod_id" && -z "$runpod_watchdog_pid" ]] || return 0
      runpod_watchdog_failure_file="$(mktemp "${TMPDIR:-/tmp}/rtf-runpod-watchdog.XXXXXX")"
      : > "$runpod_watchdog_failure_file"
      (
        consecutive_failures=0
        while true; do
          pod_watchdog_state="$(timeout 30s runpodctl pod get "$pod_id" --output json 2>/dev/null || true)"
          pod_watchdog_list="$(timeout 30s runpodctl pod list --all --name "$RTF_RUN_ID" --output json 2>/dev/null || true)"
          pod_watchdog_exists="$(jq -er --arg pod_id "$pod_id" '[.[] | select((.id // .podId // .pod_id) == $pod_id)] | length > 0' <<<"$pod_watchdog_list" 2>/dev/null || echo false)"
          pod_watchdog_status="$(jq -r '(.runtimeStatus // .runtime_status // .runtime.status // .desiredStatus // .desired_status // "") | ascii_downcase' <<<"$pod_watchdog_state" 2>/dev/null || true)"
          echo "RunPod heartbeat: pod_id=$pod_id exists=$pod_watchdog_exists status=${pod_watchdog_status:-unknown}" >&2
          pod_watchdog_gpu_telemetry="$(runpod_ssh nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits 2>&1 || true)"
          pod_watchdog_gpu_error_diagnostic="$(runpod_ssh nvidia-smi -q -d ECC 2>&1 | grep -Ei 'error|xid|retired|volatile|aggregate' | head -n 40 || true)"
          pod_watchdog_telemetry_summary="$(tr '\r\n' '  ' <<<"$pod_watchdog_gpu_telemetry" | cut -c1-1000)"
          pod_watchdog_error_summary="$(tr '\r\n' '  ' <<<"$pod_watchdog_gpu_error_diagnostic" | cut -c1-1000)"
          echo "RunPod GPU heartbeat: pod_id=$pod_id telemetry=${pod_watchdog_telemetry_summary:-unavailable}" >&2
          [[ -n "$pod_watchdog_error_summary" ]] && echo "::warning::RunPod GPU diagnostic: pod_id=$pod_id errors=$pod_watchdog_error_summary" >&2
          pod_watchdog_container_log_tail=""
          if [[ "$pod_watchdog_exists" == true && "$pod_watchdog_status" != exited && "$pod_watchdog_status" != terminated ]]; then
            consecutive_failures=0
          else
            consecutive_failures=$((consecutive_failures + 1))
          fi
          if (( consecutive_failures >= 3 )); then
            pod_watchdog_container_log_tail="$(runpodctl pod logs "$pod_id" --source container --tail 200 2>&1 || true)"
            pod_state_json="$pod_watchdog_state"
            pod_list_state_json="$pod_watchdog_list"
            ssh_info_json=""
            ssh_info_diagnostic=""
            write_runpod_diagnostics watchdog RUNPOD_POD_LOST "Pod disappeared or stopped during benchmark; last GPU telemetry and container log tail were collected"
            {
              printf '%s\n' "RUNPOD_POD_LOST: Pod disappeared or stopped during benchmark"
              printf 'last_gpu_telemetry=%s\n' "$(tr '\r\n' '  ' <<<"$pod_watchdog_gpu_telemetry" | cut -c1-1000)"
              printf 'last_gpu_error_diagnostic=%s\n' "$(tr '\r\n' '  ' <<<"$pod_watchdog_gpu_error_diagnostic" | cut -c1-1000)"
              printf 'container_log_tail=%s\n' "$(tr '\r\n' '  ' <<<"$pod_watchdog_container_log_tail" | cut -c1-2000)"
            } > "$runpod_watchdog_failure_file"
            exit 1
          fi
          sleep "$RTF_RUNPOD_HEARTBEAT_SECONDS"
        done
      ) &
      runpod_watchdog_pid=$!
    }
    stop_runpod_pod_watchdog() {
      [[ -n "$runpod_watchdog_pid" ]] || return 0
      kill "$runpod_watchdog_pid" 2>/dev/null || true
      wait "$runpod_watchdog_pid" 2>/dev/null || true
      runpod_watchdog_pid=""
    }
    write_runpod_blocked_receipt() {
      local failure_code="$1"
      local error_message="$2"
      local job_id="${3:-}"
      mkdir -p "$(dirname "${RTF_LOCAL_RECEIPT:-result-receipt.json}")"
      jq -n \
        --arg run_id "$RTF_RUN_ID" --arg job_id "$job_id" --arg error_code "$failure_code" \
        --arg error_message "$error_message" \
        --arg model_id "$RTF_MODEL_ID" --arg model_revision "$RTF_MODEL_REVISION" \
        --arg dataset_id "$RTF_DATASET_ID" --arg dataset_revision "$RTF_DATASET_REVISION" \
        --arg image_digest "$RTF_IMAGE_DIGEST" --arg fixture_repo_id "$RTF_FIXTURE_REPO_ID" \
        --arg fixture_revision "$RTF_FIXTURE_REVISION" --arg manifest_sha256 "$RTF_FIXTURE_MANIFEST_SHA256" \
        --arg gpu "$RTF_GPU" --arg profile "$RTF_INSPECTION_PROFILE" --arg batch_size "$RTF_BATCH_SIZE" \
        '{schema_version:1,run_id:$run_id,status:"blocked",job_id:($job_id | if length == 0 then null else . end),result_uri:null,result_sha256:null,metrics_uri:null,metrics_sha256:null,error_code:$error_code,error_message:$error_message,model_id:$model_id,model_revision:$model_revision,dataset_id:$dataset_id,dataset_revision:$dataset_revision,image_digest:$image_digest,fixture_repo_id:$fixture_repo_id,fixture_revision:$fixture_revision,manifest_sha256:$manifest_sha256,provider:"cuda",environment:"linux",service_id:"runpod-pod",gpu:$gpu,inspection_profile:$profile,batch_size:($batch_size|tonumber)}' \
        > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
    }
    abort_runpod_preflight() {
      local phase="$1"
      local preflight_output="$2"
      local failure_code failure_message
      failure_code="$(grep '^RUNPOD_PREFLIGHT_FAILURE_CODE=' <<<"$preflight_output" | tail -n1 | cut -d= -f2-)"
      failure_message="$(grep '^RUNPOD_PREFLIGHT_FAILURE_MESSAGE=' <<<"$preflight_output" | tail -n1 | cut -d= -f2-)"
      failure_code="${failure_code:-RUNPOD_EXECUTION_PREFLIGHT_FAILED}"
      failure_message="${failure_message:-RunPod execution preflight failed}"
      echo "::error::$failure_message" >&2
      write_runpod_diagnostics "execution_preflight_${phase}" "$failure_code" "$failure_message"
      write_runpod_blocked_receipt "$failure_code" "$failure_message" "${pod_id:-}"
      if [[ "$phase" == remote && -n "$pod_id" ]]; then
        stop_runpod_pod_watchdog || true
        stop_runpod_container_logs || true
        delete_pod || true
        pod_create_failed=0
      fi
      exit 1
    }
    write_runpod_diagnostics() {
      local phase="$1"
      local error_code="${2:-}"
      local error_message="${3:-}"
      [[ -n "$RTF_LOCAL_PROVIDER_DIAGNOSTICS" ]] || return 0
      mkdir -p "$(dirname "$RTF_LOCAL_PROVIDER_DIAGNOSTICS")"
      jq -n \
        --arg schema_version 1 --arg run_id "$RTF_RUN_ID" --arg pod_id "${pod_id:-}" \
        --arg phase "$phase" --arg error_code "$error_code" --arg error_message "$error_message" \
        --arg image_digest "$RTF_IMAGE_DIGEST" --arg gpu "$RTF_GPU" \
        --arg pod_get "${pod_state_json:-}" --arg pod_list "${pod_list_state_json:-}" \
        --arg ssh_info "${ssh_info_json:-}" --arg ssh_diagnostic "${ssh_info_diagnostic:-}" \
        --arg gpu_telemetry "${pod_watchdog_gpu_telemetry:-}" \
        --arg gpu_error_diagnostic "${pod_watchdog_gpu_error_diagnostic:-}" \
        --arg container_log_tail "${pod_watchdog_container_log_tail:-}" \
        --arg observed_at "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
        '{schema_version:($schema_version|tonumber),run_id:$run_id,pod_id:($pod_id|if length == 0 then null else . end),phase:$phase,error_code:($error_code|if length == 0 then null else . end),error_message:($error_message|if length == 0 then null else . end),image_digest:$image_digest,gpu:$gpu,observed_at:$observed_at,pod_get_raw:($pod_get|if length == 0 then null else . end),pod_list_raw:($pod_list|if length == 0 then null else . end),ssh_info_raw:($ssh_info|if length == 0 then null else . end),ssh_diagnostic:($ssh_diagnostic|if length == 0 then null else . end),gpu_telemetry:($gpu_telemetry|if length == 0 then null else . end),gpu_error_diagnostic:($gpu_error_diagnostic|if length == 0 then null else . end),container_log_tail:($container_log_tail|if length == 0 then null else . end)}' \
        > "$RTF_LOCAL_PROVIDER_DIAGNOSTICS"
    }
    # GitHub cancellation can signal the shell while `pod create` is still
    # waiting for the provider. Handle signals explicitly; an EXIT-only trap
    # is not sufficient to prevent a rented Pod from surviving cancellation.
    cleanup_on_signal() {
      cleanup_runpod
      exit 143
    }
    trap cleanup_runpod EXIT
    trap cleanup_on_signal INT TERM HUP
    [[ "$RTF_RUNPOD_MAX_HOURS" =~ ^[1-9][0-9]*$ && "$RTF_RUNPOD_MAX_HOURS" -le 168 ]] || {
      echo 'RTF_RUNPOD_MAX_HOURS must be an integer between 1 and 168' >&2
      exit 2
    }
    [[ "$RTF_RUNPOD_CREATE_TIMEOUT_MINUTES" =~ ^[1-9][0-9]*$ ]] || {
      echo 'RTF_RUNPOD_CREATE_TIMEOUT_MINUTES must be a positive integer' >&2
      exit 2
    }
    [[ "$RTF_RUNPOD_WAIT_TIMEOUT_MINUTES" =~ ^[1-9][0-9]*$ ]] || {
      echo 'RTF_RUNPOD_WAIT_TIMEOUT_MINUTES must be a positive integer' >&2
      exit 2
    }
    [[ "$RTF_RUNPOD_POLL_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
      echo 'RTF_RUNPOD_POLL_SECONDS must be a positive integer' >&2
      exit 2
    }
    [[ "$RTF_RUNPOD_SSH_PROBE_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
      echo 'RTF_RUNPOD_SSH_PROBE_TIMEOUT_SECONDS must be a positive integer' >&2
      exit 2
    }
    [[ "$RTF_RUNPOD_SSH_CONNECT_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
      echo 'RTF_RUNPOD_SSH_CONNECT_TIMEOUT_SECONDS must be a positive integer' >&2
      exit 2
    }
    [[ "$RTF_RUNPOD_SSH_INFO_WAIT_MINUTES" =~ ^[1-9][0-9]*$ ]] || {
      echo 'RTF_RUNPOD_SSH_INFO_WAIT_MINUTES must be a positive integer' >&2
      exit 2
    }
    [[ "$RTF_RUNPOD_HEARTBEAT_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
      echo 'RTF_RUNPOD_HEARTBEAT_SECONDS must be a positive integer' >&2
      exit 2
    }
    [[ -z "$RTF_RUNPOD_MIN_CUDA_VERSION" || "$RTF_RUNPOD_MIN_CUDA_VERSION" =~ ^[0-9]+\.[0-9]+$ ]] || {
      echo 'RTF_RUNPOD_MIN_CUDA_VERSION must be a CUDA major.minor version' >&2
      exit 2
    }
    runpod_wait_timeout="${RTF_RUNPOD_WAIT_TIMEOUT_MINUTES}m"
    # runpodctl v2.11.0 forwards this field to the GraphQL DateTime scalar.
    # Calculate an absolute UTC timestamp locally; --wait-timeout remains a
    # duration because it is a CLI readiness wait.
    terminate_after="$(date -u -d "+${RTF_RUNPOD_MAX_HOURS} hours" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || true)"
    if [[ -z "$terminate_after" ]]; then
      # BSD date (for local macOS execution) uses a different flag shape.
      terminate_after="$(date -u -v+${RTF_RUNPOD_MAX_HOURS}H '+%Y-%m-%dT%H:%M:%SZ')"
    fi
    [[ "$terminate_after" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || {
      echo "failed to generate RunPod termination deadline: $terminate_after" >&2
      exit 2
    }
    echo "RunPod pod create timeout: ${RTF_RUNPOD_CREATE_TIMEOUT_MINUTES}m; readiness timeout: $runpod_wait_timeout; SSH info grace: ${RTF_RUNPOD_SSH_INFO_WAIT_MINUTES}m; termination deadline: $terminate_after" >&2
    echo "::group::RunPod runner preflight"
    set +e
    runner_preflight_output="$(bash scripts/ci/run-runpod-execution-preflight.sh --phase runner 2>&1)"
    runner_preflight_status=$?
    set -e
    printf '%s\n' "$runner_preflight_output" >&2
    echo '::endgroup::'
    if (( runner_preflight_status != 0 )); then
      abort_runpod_preflight runner "$runner_preflight_output"
    fi
    # Do not put HF_TOKEN or benchmark configuration into RunPod Pod
    # metadata. Provider-side env handling has varied across runpodctl
    # versions, and Pod metadata is visible to provider control-plane reads.
    # The authoritative payload is transferred over the already authenticated
    # SSH channel after readiness and written root-only on the Pod.
    # `runpodctl pod create` can block while the provider schedules a Pod or
    # pulls the image, without emitting output. Keep that phase bounded and
    # observable; the EXIT trap also removes an orphan Pod found by name if
    # the client is killed after the provider accepted the request.
    create_log="$(mktemp "${TMPDIR:-/tmp}/rtf-runpod-create.XXXXXX")"
    create_started="$(date +%s)"
    pod_create_timed_out=0
    pod_create_discovered=0
    # Treat the request as potentially accepted until the response is parsed.
    # This makes signal cleanup search for a Pod by its unique run ID even if
    # runpodctl is terminated before returning the Pod ID.
    pod_create_failed=1
    set +e
    [[ "$RTF_RUNPOD_CLOUD_TYPE" == auto || "$RTF_RUNPOD_CLOUD_TYPE" == SECURE || "$RTF_RUNPOD_CLOUD_TYPE" == COMMUNITY ]] || {
      echo 'RTF_RUNPOD_CLOUD_TYPE must be auto, SECURE, or COMMUNITY' >&2
      exit 2
    }
    if [[ "$RTF_RUNPOD_CLOUD_TYPE" == auto ]]; then
      gpu_inventory=""
      inventory_attempts=3
      inventory_retry_seconds=20
      for inventory_attempt in $(seq 1 "$inventory_attempts"); do
        gpu_inventory="$(runpodctl gpu list --include-unavailable --output json 2>&1 || true)"
        secure_available="$(jq -er --arg gpu "$RUNPOD_GPU_ID" '[.[] | select((.gpuId // .gpu_id) == $gpu and .available == true and (.secureCloud // .secure_cloud) == true)] | length > 0' <<<"$gpu_inventory" 2>/dev/null || echo false)"
        community_available="$(jq -er --arg gpu "$RUNPOD_GPU_ID" '[.[] | select((.gpuId // .gpu_id) == $gpu and .available == true and (.communityCloud // .community_cloud) == true)] | length > 0' <<<"$gpu_inventory" 2>/dev/null || echo false)"
        if [[ "$secure_available" == true || "$community_available" == true ]]; then
          break
        fi
        if [[ "$inventory_attempt" -lt "$inventory_attempts" ]]; then
          echo "RunPod auto cloud inventory retry: attempt=$inventory_attempt/$inventory_attempts gpu=$RUNPOD_GPU_ID secure=$secure_available community=$community_available" >&2
          sleep $((inventory_retry_seconds * inventory_attempt))
        fi
      done
      if [[ "$secure_available" == true ]]; then
        RTF_RUNPOD_CLOUD_TYPE=SECURE
      elif [[ "$community_available" == true ]]; then
        RTF_RUNPOD_CLOUD_TYPE=COMMUNITY
      else
        echo "RUNPOD_GPU_NOT_AVAILABLE: inventory has no available SECURE or COMMUNITY capacity for $RUNPOD_GPU_ID" >&2
        echo "$gpu_inventory" | jq . >&2 2>/dev/null || echo "$gpu_inventory" >&2
        exit 1
      fi
    fi
    echo "RunPod scheduling: gpu=$RUNPOD_GPU_ID cloud_type=$RTF_RUNPOD_CLOUD_TYPE min_cuda=${RTF_RUNPOD_MIN_CUDA_VERSION:-any}" >&2
    runpod_create_args=(
      pod create --name "${RTF_RUN_ID}" --image "$IMAGE"
      --cloud-type "$RTF_RUNPOD_CLOUD_TYPE" --gpu-id "$RUNPOD_GPU_ID" --ssh
      --ports 22/tcp --terminate-after "$terminate_after"
    )
    if [[ -n "$RTF_RUNPOD_MIN_CUDA_VERSION" ]]; then
      runpod_create_args+=(--min-cuda-version "$RTF_RUNPOD_MIN_CUDA_VERSION")
    fi
    if [[ -n "${RUNPOD_REGISTRY_AUTH_ID:-}" ]]; then
      runpod_create_args+=(--registry-auth-id "$RUNPOD_REGISTRY_AUTH_ID")
    fi
    runpodctl "${runpod_create_args[@]}" \
      --output json >"$create_log" 2>&1 &
    pod_create_pid=$!
    pod_create_status=124
    while kill -0 "$pod_create_pid" 2>/dev/null; do
      # Some runpodctl versions keep the create request open until a later
      # lifecycle event even after the API has rented the named Pod. Discover
      # the exact Pod independently so container/readiness polling can begin.
      discovered_pod_id="$(runpodctl pod list --all --name "$RTF_RUN_ID" --output json 2>/dev/null \
        | jq -er '.[] | (.id // .podId // .pod_id) // empty' 2>/dev/null | head -n 1 || true)"
      if [[ -n "$discovered_pod_id" ]]; then
        pod_id="$discovered_pod_id"
        pod_create_discovered=1
        echo "RunPod phase=pod_create discovered pod_id=$pod_id from named Pod list" >&2
        kill "$pod_create_pid" 2>/dev/null || true
        break
      fi
      create_elapsed=$(( $(date +%s) - create_started ))
      echo "RunPod phase=pod_create elapsed=${create_elapsed}s timeout=${RTF_RUNPOD_CREATE_TIMEOUT_MINUTES}m" >&2
      if (( create_elapsed >= RTF_RUNPOD_CREATE_TIMEOUT_MINUTES * 60 )); then
        pod_create_timed_out=1
        kill "$pod_create_pid" 2>/dev/null || true
        break
      fi
      sleep "$RTF_RUNPOD_POLL_SECONDS"
    done
    if [[ "$pod_create_discovered" -eq 1 ]]; then
      wait "$pod_create_pid" 2>/dev/null || true
      pod_create_status=0
      pod_json="{\"id\":\"$pod_id\"}"
    elif [[ "$pod_create_timed_out" -eq 1 ]]; then
      wait "$pod_create_pid" 2>/dev/null || true
      pod_create_status=124
      pod_json="$(<"$create_log")"
    else
      wait "$pod_create_pid"
      pod_create_status=$?
      pod_json="$(<"$create_log")"
    fi
    rm -f "$create_log"
    set -e
    # `jq -e` prints JSON null before returning failure for an error response;
    # use `// empty` so the literal string "null" can never reach pod delete.
    pod_id="$(jq -er '(.id // .podId // .pod_id) // empty' <<<"$pod_json" 2>/dev/null || true)"
    if [[ "$pod_create_status" -ne 0 || -z "$pod_id" ]]; then
      pod_create_failed=1
      printf '%s\n' "$pod_json" >&2
      echo "::error::RunPod pod create failed: exit_status=$pod_create_status timed_out=$pod_create_timed_out pod_id=${pod_id:-<none>}" >&2
      log_runpod_response "pod create" "$pod_json"
      failure_code="PROVIDER_RUNPOD_POD_CREATE_FAILED"
      failure_message="RunPod Pod creation failed before remote execution"
      if [[ "$pod_create_timed_out" -eq 1 ]]; then
        failure_code="RUNPOD_POD_CREATE_TIMEOUT"
        failure_message="RunPod Pod creation timed out before remote execution"
      elif grep -Eqi 'balance is too low|insufficient balance|add funds to your account' <<<"$pod_json"; then
        failure_code="RUNPOD_ACCOUNT_BALANCE_TOO_LOW"
      elif grep -Eqi 'cuda|nvidia driver|driver version|unsupported cuda' <<<"$pod_json"; then
        failure_code="RUNPOD_CUDA_REQUIREMENT_UNSATISFIED"
        failure_message="RunPod could not schedule the Pod with the required CUDA ${RTF_RUNPOD_MIN_CUDA_VERSION} floor"
      elif grep -Eqi 'no longer any instances available|no instances available|insufficient capacity' <<<"$pod_json"; then
        failure_code="RUNPOD_NO_INSTANCE_AVAILABLE"
      elif grep -Eqi 'DateTime cannot represent|invalid date-time-string' <<<"$pod_json"; then
        failure_code="RUNPOD_TERMINATE_AFTER_INVALID"
      fi
      pod_state_json=""
      pod_list_state_json="$pod_json"
      ssh_info_json=""
      ssh_info_diagnostic=""
      write_runpod_diagnostics pod_create "$failure_code" "RunPod Pod creation failed before remote execution"
      mkdir -p "$(dirname "${RTF_LOCAL_RECEIPT:-result-receipt.json}")"
      jq -n \
        --arg run_id "$RTF_RUN_ID" --arg job_id "$pod_id" --arg error_code "$failure_code" \
        --arg error_message "$failure_message: $pod_json" \
        --arg model_id "$RTF_MODEL_ID" --arg model_revision "$RTF_MODEL_REVISION" \
        --arg dataset_id "$RTF_DATASET_ID" --arg dataset_revision "$RTF_DATASET_REVISION" \
        --arg image_digest "$RTF_IMAGE_DIGEST" --arg fixture_repo_id "$RTF_FIXTURE_REPO_ID" \
        --arg fixture_revision "$RTF_FIXTURE_REVISION" --arg manifest_sha256 "$RTF_FIXTURE_MANIFEST_SHA256" \
        --arg gpu "$RTF_GPU" --arg profile "$RTF_INSPECTION_PROFILE" --arg batch_size "$RTF_BATCH_SIZE" \
        '{schema_version:1,run_id:$run_id,status:"blocked",job_id:($job_id | if length == 0 then null else . end),result_uri:null,result_sha256:null,metrics_uri:null,metrics_sha256:null,error_code:$error_code,error_message:$error_message,model_id:$model_id,model_revision:$model_revision,dataset_id:$dataset_id,dataset_revision:$dataset_revision,image_digest:$image_digest,fixture_repo_id:$fixture_repo_id,fixture_revision:$fixture_revision,manifest_sha256:$manifest_sha256,provider:"cuda",environment:"linux",service_id:"runpod-pod",gpu:$gpu,inspection_profile:$profile,batch_size:($batch_size|tonumber)}' \
        > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
      [[ "$pod_create_status" -ne 0 ]] && exit "$pod_create_status"
      echo 'RunPod pod create did not return a pod id' >&2
      exit 1
    fi
    pod_create_failed=0
    readiness_deadline=$(( $(date +%s) + RTF_RUNPOD_WAIT_TIMEOUT_MINUTES * 60 ))
    pod_ready=0
    RTF_QUEUE_LATENCY_SEC=""
    runtime_ready_since=0
    readiness_error_code="RUNPOD_READINESS_TIMEOUT"
    while [[ "$(date +%s)" -lt "$readiness_deadline" ]]; do
      if pod_state_json="$(runpodctl pod get "$pod_id" --output json 2>&1)"; then
        pod_get_status=0
      else
        pod_get_status=$?
      fi
      # The CLI's `pod get` and `pod list` responses are not schema-identical.
      # In particular, current list responses expose runtimeStatus while some
      # get responses expose desiredStatus/runtime. Poll both representations
      # for the exact Pod ID instead of treating a valid running Pod as absent.
      if pod_list_state_json="$(runpodctl pod list --all --name "$RTF_RUN_ID" --output json 2>&1)"; then
        pod_list_status=0
      else
        pod_list_status=$?
      fi
      pod_state_summary="$(jq -c --arg pod_id "$pod_id" \
        '{get:{id:(.id // .podId // .pod_id),desiredStatus:(.desiredStatus // .desired_status),runtimeAvailable:(.runtime != null),lastStatusChange},pod_id:$pod_id}' \
        <<<"$pod_state_json" 2>/dev/null || true)"
      pod_list_summary="$(jq -c --arg pod_id "$pod_id" \
        '[.[] | select((.id // .podId // .pod_id) == $pod_id) | {id:(.id // .podId // .pod_id),runtimeStatus:(.runtimeStatus // .runtime_status),desiredStatus:(.desiredStatus // .desired_status)}] | first // {}' \
        <<<"$pod_list_state_json" 2>/dev/null || true)"
      if ssh_info_json="$(runpodctl ssh info "$pod_id" --output json 2>&1)"; then
        ssh_info_status=0
      else
        ssh_info_status=$?
      fi
      ssh_probe_command="$(jq -er '(.sshCommand // .ssh_command) // empty' <<<"$ssh_info_json" 2>/dev/null || true)"
      ssh_info_diagnostic="$(jq -r '(.code // .errorCode // .error_code // .message // .error) // empty' \
        <<<"$ssh_info_json" 2>/dev/null | tr '\r\n' '  ' | cut -c1-160 || true)"
      if [[ -n "$ssh_probe_command" ]]; then
        ssh_probe_command="$(decorate_runpod_ssh_command "$ssh_probe_command" "$RTF_RUNPOD_SSH_PROBE_TIMEOUT_SECONDS" || true)"
      fi
      [[ -n "$pod_state_summary" ]] && echo "RunPod pod readiness: $pod_state_summary" >&2
      [[ -n "$pod_list_summary" ]] && echo "RunPod pod list readiness: $pod_list_summary" >&2
      echo "RunPod readiness poll: pod_get_exit=$pod_get_status pod_list_exit=$pod_list_status ssh_info_exit=$ssh_info_status ssh_command_present=$([[ -n "$ssh_probe_command" ]] && echo true || echo false)" >&2
      (( pod_get_status == 0 )) || log_runpod_response "pod get" "$pod_state_json"
      (( pod_list_status == 0 )) || log_runpod_response "pod list" "$pod_list_state_json"
      (( ssh_info_status == 0 )) || log_runpod_response "ssh info" "$ssh_info_json"
      write_runpod_diagnostics readiness_poll "" ""
      if jq -e '(.desiredStatus == "RUNNING") and (.runtime != null)' <<<"$pod_state_json" >/dev/null 2>&1 || \
        jq -e '((.runtimeStatus // "") | ascii_downcase) == "running"' <<<"$pod_list_summary" >/dev/null 2>&1; then
        if [[ "$runtime_ready_since" -eq 0 ]]; then
          runtime_ready_since="$(date +%s)"
        fi
        # RUNNING only means the Pod lifecycle reached running. Require an
        # actual SSH handshake before invoking the benchmark entrypoint;
        # otherwise the provider may still be publishing the SSH port.
        ssh_ready=0
        if [[ -n "$ssh_probe_command" ]] && \
          timeout --signal=TERM "${RTF_RUNPOD_SSH_PROBE_TIMEOUT_SECONDS}s" \
            bash -c "$ssh_probe_command true" >/dev/null 2>&1; then
          ssh_ready=1
        fi
        ssh_command_present=false
        ssh_ready_text=false
        [[ -n "$ssh_probe_command" ]] && ssh_command_present=true
        [[ "$ssh_ready" -eq 1 ]] && ssh_ready_text=true
        echo "RunPod SSH readiness: command_present=$ssh_command_present ready=$ssh_ready_text${ssh_info_diagnostic:+ diagnostic=$ssh_info_diagnostic}" >&2
        if [[ "$ssh_ready" -eq 1 ]]; then
          pod_ready=1
          RTF_QUEUE_LATENCY_SEC="$(( $(date +%s) - create_started ))"
          break
        fi
        if (( $(date +%s) - runtime_ready_since >= RTF_RUNPOD_SSH_INFO_WAIT_MINUTES * 60 )); then
          readiness_error_code="RUNPOD_SSH_INFO_UNAVAILABLE"
          break
        fi
      fi
      if jq -e '(.desiredStatus == "EXITED") or (.desiredStatus == "TERMINATED")' <<<"$pod_state_json" >/dev/null 2>&1 || \
        jq -e '((.desiredStatus // "") | ascii_upcase) == "EXITED" or ((.desiredStatus // "") | ascii_upcase) == "TERMINATED"' <<<"$pod_list_summary" >/dev/null 2>&1; then
        break
      fi
      sleep "$RTF_RUNPOD_POLL_SECONDS"
    done
    if [[ "$pod_ready" -ne 1 ]]; then
      failure_code="$readiness_error_code"
      if jq -e '(.desiredStatus == "EXITED") or (.desiredStatus == "TERMINATED")' <<<"${pod_state_json:-}" >/dev/null 2>&1; then
        failure_code="RUNPOD_POD_EXITED_BEFORE_READINESS"
      fi
      if grep -Eqi 'cuda|nvidia driver|driver version|unsupported cuda' <<<"${pod_state_json:-} ${pod_list_state_json:-}"; then
        failure_code="RUNPOD_CUDA_REQUIREMENT_UNSATISFIED"
      fi
      mkdir -p "$(dirname "${RTF_LOCAL_RECEIPT:-result-receipt.json}")"
      error_message="RunPod Pod did not become SSH-ready; provider SSH info was unavailable after the bounded readiness grace"
      if [[ "$failure_code" == RUNPOD_CUDA_REQUIREMENT_UNSATISFIED ]]; then
        error_message="RunPod Pod did not become ready because CUDA/driver compatibility failed for the required CUDA ${RTF_RUNPOD_MIN_CUDA_VERSION} floor"
      fi
      if [[ -n "${ssh_info_diagnostic:-}" ]]; then
        error_message="$error_message: $ssh_info_diagnostic"
      fi
      echo "::error::RunPod readiness failed: code=$failure_code pod_id=$pod_id ssh_info_exit=${ssh_info_status:-unknown} diagnostic=${ssh_info_diagnostic:-<none>}" >&2
      log_runpod_response "last ssh info" "${ssh_info_json:-}"
      write_runpod_diagnostics readiness_failed "$failure_code" "$error_message"
      jq -n \
        --arg run_id "$RTF_RUN_ID" --arg job_id "$pod_id" --arg error_code "$failure_code" \
        --arg error_message "$error_message" \
        --arg model_id "$RTF_MODEL_ID" --arg model_revision "$RTF_MODEL_REVISION" \
        --arg dataset_id "$RTF_DATASET_ID" --arg dataset_revision "$RTF_DATASET_REVISION" \
        --arg image_digest "$RTF_IMAGE_DIGEST" --arg fixture_repo_id "$RTF_FIXTURE_REPO_ID" \
        --arg fixture_revision "$RTF_FIXTURE_REVISION" --arg manifest_sha256 "$RTF_FIXTURE_MANIFEST_SHA256" \
        --arg gpu "$RTF_GPU" --arg profile "$RTF_INSPECTION_PROFILE" --arg batch_size "$RTF_BATCH_SIZE" \
        '{schema_version:1,run_id:$run_id,status:"blocked",job_id:$job_id,result_uri:null,result_sha256:null,metrics_uri:null,metrics_sha256:null,error_code:$error_code,error_message:$error_message,model_id:$model_id,model_revision:$model_revision,dataset_id:$dataset_id,dataset_revision:$dataset_revision,image_digest:$image_digest,fixture_repo_id:$fixture_repo_id,fixture_revision:$fixture_revision,manifest_sha256:$manifest_sha256,provider:"cuda",environment:"linux",service_id:"runpod-pod",gpu:$gpu,inspection_profile:$profile,batch_size:($batch_size|tonumber)}' \
        > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
      exit 1
    fi
    # RunPod exposes the rented GPU price on `pod get` as costPerHr. Capture
    # it from the provider response and pass it to the container; a missing
    # price must never become a completed result with a null cost metric.
    RTF_GPU_PRICE_PER_HOUR="$(jq -er '(.adjustedCostPerHr // .adjusted_cost_per_hr // .costPerHr // .cost_per_hr) | if type == "number" then . elif type == "string" then tonumber else error end | select(isfinite and . >= 0)' <<<"$pod_state_json" 2>/dev/null || true)"
    if [[ -z "$RTF_GPU_PRICE_PER_HOUR" ]]; then
      failure_code="RUNPOD_GPU_PRICE_UNAVAILABLE"
      error_message="RunPod Pod became SSH-ready but pod get did not expose costPerHr"
      write_runpod_diagnostics metrics_preflight "$failure_code" "$error_message"
      mkdir -p "$(dirname "${RTF_LOCAL_RECEIPT:-result-receipt.json}")"
      jq -n \
        --arg run_id "$RTF_RUN_ID" --arg job_id "$pod_id" --arg error_code "$failure_code" \
        --arg error_message "$error_message" \
        --arg model_id "$RTF_MODEL_ID" --arg model_revision "$RTF_MODEL_REVISION" \
        --arg dataset_id "$RTF_DATASET_ID" --arg dataset_revision "$RTF_DATASET_REVISION" \
        --arg image_digest "$RTF_IMAGE_DIGEST" --arg fixture_repo_id "$RTF_FIXTURE_REPO_ID" \
        --arg fixture_revision "$RTF_FIXTURE_REVISION" --arg manifest_sha256 "$RTF_FIXTURE_MANIFEST_SHA256" \
        --arg gpu "$RTF_GPU" --arg profile "$RTF_INSPECTION_PROFILE" --arg batch_size "$RTF_BATCH_SIZE" \
        '{schema_version:1,run_id:$run_id,status:"blocked",job_id:$job_id,result_uri:null,result_sha256:null,metrics_uri:null,metrics_sha256:null,error_code:$error_code,error_message:$error_message,model_id:$model_id,model_revision:$model_revision,dataset_id:$dataset_id,dataset_revision:$dataset_revision,image_digest:$image_digest,fixture_repo_id:$fixture_repo_id,fixture_revision:$fixture_revision,manifest_sha256:$manifest_sha256,provider:"cuda",environment:"linux",service_id:"runpod-pod",gpu:$gpu,inspection_profile:$profile,batch_size:($batch_size|tonumber)}' \
        > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
      exit 1
    fi
    start_runpod_container_logs
    # runpodctl releases have emitted both camelCase and snake_case JSON keys.
    # Accept only a non-empty command from either spelling; do not synthesize
    # an SSH endpoint from an incomplete response.
    if ssh_info_json="$(runpodctl ssh info "$pod_id" --output json 2>&1)"; then
      ssh_info_status=0
    else
      ssh_info_status=$?
    fi
    ssh_command="$(jq -er '(.sshCommand // .ssh_command) // empty' <<<"$ssh_info_json" 2>/dev/null || true)"
    if [[ "$ssh_info_status" -ne 0 || -z "$ssh_command" ]]; then
      failure_code="RUNPOD_SSH_FAILED"
      failure_message="RunPod SSH info did not return a usable SSH command"
      echo "::error::$failure_message: exit_status=$ssh_info_status pod_id=$pod_id" >&2
      log_runpod_response "ssh info" "$ssh_info_json"
      exit 1
    fi
    ssh_command="$(decorate_runpod_ssh_command "$ssh_command" "$RTF_RUNPOD_SSH_CONNECT_TIMEOUT_SECONDS")"
    runpod_ssh() {
      local remote_command
      printf -v remote_command '%q ' "$@"
      eval "$ssh_command $remote_command"
    }
    echo "::group::RunPod remote preflight"
    set +e
    remote_preflight_output="$(bash scripts/ci/run-runpod-execution-preflight.sh \
      --phase remote \
      --pod-id "$pod_id" \
      --gpu-id "$RUNPOD_GPU_ID" \
      --min-cuda-version "${RTF_RUNPOD_MIN_CUDA_VERSION:-}" \
      --ssh-command "$ssh_command" \
      --pod-state-json "$pod_state_json" 2>&1)"
    remote_preflight_status=$?
    set -e
    printf '%s\n' "$remote_preflight_output" >&2
    echo '::endgroup::'
    if (( remote_preflight_status != 0 )); then
      abort_runpod_preflight remote "$remote_preflight_output"
    fi
    write_runpod_environment() {
      local key value
      for key in \
        RTF_RUN_ID RTF_MANIFEST RTF_OUTPUT RTF_CONTENT_OUTPUT RTF_ERROR_LOG \
        RTF_MODEL_ID RTF_MODEL_REVISION RTF_DATASET_ID RTF_DATASET_REVISION \
        RTF_DATASET_CONFIGURATION RTF_DATASET_SPLIT RTF_DATASET_SEED \
        RTF_DATASET_COUNT_MIN RTF_DATASET_COUNT_MAX RTF_DATASET_TARGET_TOTAL_SEC \
        RTF_DATASET_MAX_DURATION_SEC RTF_INSPECTION_PROFILE RTF_PROFILE_ID \
        RTF_GPU RTF_BATCH_SIZE RTF_PRECISION RTF_REPEAT RTF_DECODER RTF_QUEUE_LATENCY_SEC \
        RTF_FIXTURE_REPO_ID RTF_FIXTURE_REVISION RTF_FIXTURE_FILENAME \
        RTF_FIXTURE_MANIFEST_SHA256 RTF_CUDA_DIAGNOSTICS RTF_RESULT_REPO_ID \
        RTF_RESULT_PATH RTF_IMAGE_DIGEST RTF_GPU_PRICE_PER_HOUR \
        RTF_HF_429_WAIT_SECONDS RTF_HF_429_MAX_ATTEMPTS; do
        value="${!key:-}"
        printf '%s=%q\n' "$key" "$value"
      done
      printf 'RTF_PROVIDER=%q\n' cuda
      printf 'RTF_SERVICE_ID=%q\n' runpod-pod
      printf 'HF_TOKEN=%q\n' "${HF_TOKEN:-}"
    }
    if [[ -n "$RTF_FIXTURE_LOCAL_DIR" ]]; then
      [[ -d "$RTF_FIXTURE_LOCAL_DIR" ]] || {
        echo "RTF_FIXTURE_LOCAL_DIR does not exist: $RTF_FIXTURE_LOCAL_DIR" >&2
        exit 2
      }
      echo "Transferring runner-materialized fixture to RunPod: $RTF_FIXTURE_LOCAL_DIR -> /workspace/rtf-fixture" >&2
      runpod_ssh mkdir -p /workspace/rtf-fixture
      tar -C "$RTF_FIXTURE_LOCAL_DIR" -cf - . | runpod_ssh tar -C /workspace/rtf-fixture -xf -
    fi
    # Do not pass a compound `bash -lc` command through SSH argv. OpenSSH
    # reconstructs the remote command string and a quoted `set -a; . ...`
    # sequence can be reduced to `bash -lc set`, leaving the environment file
    # empty. Transfer the allowlisted file through stdin to a simple command.
    write_runpod_environment | runpod_ssh tee /run/rtf-benchmark.env >/dev/null
    runpod_ssh chmod 600 /run/rtf-benchmark.env
    start_runpod_pod_watchdog
    # The Pod command intentionally keeps the container alive. Invoke the
    # image entrypoint explicitly over the supported SSH path so fixture
    # loading, inference, publishing, and result collection share one path.
    remote_log="$RTF_RUNPOD_LOG"
    mkdir -p "$(dirname "$remote_log")"
    set +e
    {
      printf '%s\n' 'exec > >(tee -a /run/rtf-benchmark-container.log) 2>&1'
      printf '%s\n' 'set -a' '. /run/rtf-benchmark.env' 'set +a'
      printf 'export RTF_JOB_ID=%q\n' "$pod_id"
      printf '%s\n' 'exec /opt/rtf-benchmark/entrypoint.sh'
    } | runpod_ssh bash -s 2>&1 | tee "$remote_log"
    remote_status="${PIPESTATUS[1]}"
    set -e
    echo "RunPod benchmark SSH command finished: exit_status=$remote_status log=$remote_log" >&2
    if [[ "$remote_status" -ne 0 ]]; then
      echo "::error::RunPod benchmark remote execution failed; inspect $remote_log for container output" >&2
    fi
    write_runpod_diagnostics benchmark_execution "" ""
    # A completed provider can close the SSH channel immediately after
    # publishing its result. Preserve the machine-readable stdout contract so
    # a post-run SSH timeout cannot discard an otherwise valid receipt.
    receipt_line="$(grep '^RTF_RESULT_RECEIPT=' "$remote_log" | tail -n 1 || true)"
    content_line="$(grep '^RTF_CONTENT_PROBE=' "$remote_log" | tail -n 1 || true)"
    if [[ -n "$content_line" ]]; then
      printf '%s\n' "${content_line#RTF_CONTENT_PROBE=}" > "${RTF_LOCAL_CONTENT:-content.json}"
    fi
    if [[ -n "$receipt_line" ]]; then
      printf '%s\n' "${receipt_line#RTF_RESULT_RECEIPT=}" > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
    fi
    if [[ ! -s "${RTF_LOCAL_CONTENT:-content.json}" ]]; then
      if ! runpod_ssh cat "$RTF_CONTENT_OUTPUT" > "${RTF_LOCAL_CONTENT:-content.json}"; then
        echo "RunPod metrics content retrieval failed: remote_path=$RTF_CONTENT_OUTPUT" >&2
      fi
    fi
    if ! runpod_ssh cat "$RTF_OUTPUT" > "${RTF_LOCAL_OUTPUT:-metrics.json}"; then
      echo "RunPod metrics retrieval failed: remote_path=$RTF_OUTPUT" >&2
    fi
    if [[ ! -s "${RTF_LOCAL_RECEIPT:-result-receipt.json}" ]]; then
      if ! runpod_ssh cat "${RTF_RECEIPT:-/output/result-receipt.json}" > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"; then
        echo "RunPod receipt retrieval failed: remote_path=${RTF_RECEIPT:-/output/result-receipt.json}" >&2
      fi
    fi
    stop_runpod_pod_watchdog
    if [[ -s "$runpod_watchdog_failure_file" ]]; then
      echo "::error::$(<"$runpod_watchdog_failure_file")" >&2
    fi
    if [[ ! -s "${RTF_LOCAL_RECEIPT:-result-receipt.json}" ]]; then
      mkdir -p "$(dirname "${RTF_LOCAL_RECEIPT:-result-receipt.json}")"
      failure_code="PROVIDER_EXECUTION_FAILED"
      failure_message="RunPod execution did not produce a result receipt"
      echo "::error::${failure_message}: remote_status=$remote_status pod_id=$pod_id log=$remote_log" >&2
      if grep -Eqi 'driver .*too old|CUDA driver version is insufficient|nvidia driver on your system is too old' "$remote_log"; then
        failure_code="PROVIDER_CUDA_DRIVER_INCOMPATIBLE"
        failure_message="RunPod image CUDA runtime is incompatible with the provider NVIDIA driver"
      elif grep -Eqi 'illegal memory access|cudaErrorIllegalAddress' "$remote_log"; then
        failure_code="PROVIDER_CUDA_ILLEGAL_ACCESS"
        failure_message="RunPod benchmark terminated with a CUDA illegal memory access"
      elif grep -Eqi 'out of memory|CUDA OOM|cuda out of memory' "$remote_log"; then
        failure_code="PROVIDER_CUDA_OOM"
        failure_message="RunPod benchmark terminated with CUDA out of memory"
      fi
      jq -n \
        --arg run_id "$RTF_RUN_ID" --arg error_code "$failure_code" --arg error_message "$failure_message" \
        --arg model_id "$RTF_MODEL_ID" --arg model_revision "$RTF_MODEL_REVISION" \
        --arg dataset_id "$RTF_DATASET_ID" --arg dataset_revision "$RTF_DATASET_REVISION" \
        --arg image_digest "$RTF_IMAGE_DIGEST" --arg fixture_repo_id "$RTF_FIXTURE_REPO_ID" \
        --arg fixture_revision "$RTF_FIXTURE_REVISION" --arg manifest_sha256 "$RTF_FIXTURE_MANIFEST_SHA256" \
        --arg gpu "$RTF_GPU" --arg profile "$RTF_INSPECTION_PROFILE" --arg batch_size "$RTF_BATCH_SIZE" \
        '{schema_version:1,run_id:$run_id,status:"blocked",job_id:null,result_uri:null,result_sha256:null,metrics_uri:null,metrics_sha256:null,error_code:$error_code,error_message:$error_message,model_id:$model_id,model_revision:$model_revision,dataset_id:$dataset_id,dataset_revision:$dataset_revision,image_digest:$image_digest,fixture_repo_id:$fixture_repo_id,fixture_revision:$fixture_revision,manifest_sha256:$manifest_sha256,provider:"cuda",environment:"linux",service_id:"runpod-pod",gpu:$gpu,inspection_profile:$profile,batch_size:($batch_size|tonumber)}' \
        > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
    fi
    receipt_completed=false
    if jq -e '.status == "completed"' "${RTF_LOCAL_RECEIPT:-result-receipt.json}" >/dev/null 2>&1; then
      receipt_completed=true
    fi
    if [[ "$remote_status" -ne 0 && "$receipt_completed" != true ]]; then
      exit "$remote_status"
    fi
    if [[ "$receipt_completed" == true ]]; then
      metadata_script="scripts/ci/enrich_runpod_job_metrics.py"
      [[ -f "$metadata_script" ]] || { echo "RunPod billing metadata collector is missing: $metadata_script" >&2; exit 2; }
      # Billing history is keyed by the live Pod ID. Collect and bind it
      # before deletion; the EXIT trap deletes the Pod if enrichment fails.
      if ! python "$metadata_script" --receipt "${RTF_LOCAL_RECEIPT:-result-receipt.json}"; then
        jq '.status = "blocked" | .error_code = "RUNPOD_BILLING_METADATA_UNAVAILABLE" | .error_message = "RunPod billing history could not be collected; metrics were not accepted for ranking"' \
          "${RTF_LOCAL_RECEIPT:-result-receipt.json}" > "${RTF_LOCAL_RECEIPT:-result-receipt.json}.tmp"
        mv "${RTF_LOCAL_RECEIPT:-result-receipt.json}.tmp" "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
        exit 1
      fi
    fi
    stop_runpod_container_logs
    # Delete only after metrics, receipt, and RunPod billing metadata have
    # been collected. The EXIT trap remains on the failure path as a safety net.
    delete_pod
    ;;
esac
