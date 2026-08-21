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
: "${RTF_RUNPOD_MAX_HOURS:=2}"
: "${RTF_FIXTURE_FILENAME:=benchmark-v1.jsonl}"
: "${RTF_FIXTURE_MANIFEST_SHA256:=}"
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
    l4) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA L4}" ;;
    rtx3090) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA GeForce RTX 3090}" ;;
    rtx4090) RUNPOD_GPU_ID="${RUNPOD_GPU_ID:-NVIDIA GeForce RTX 4090}" ;;
    *) echo "RunPod GPU has no Phase 1 GPU ID mapping: $RTF_GPU" >&2; exit 2 ;;
  esac
fi

case "$PROVIDER:$RTF_GPU" in
  hf:t4|hf:l4|runpod:a5000|runpod:l4|runpod:rtx3090|runpod:rtx4090) ;;
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
      -e "RTF_CUDA_DIAGNOSTICS=${RTF_CUDA_DIAGNOSTICS:-0}"
      -e "RTF_NUM_WORKERS=${RTF_NUM_WORKERS:-0}"
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
    [[ "$hf_status" -eq 0 ]] || exit "$hf_status"
    ;;
  runpod)
    command -v runpodctl >/dev/null || { echo "runpodctl is required" >&2; exit 1; }
    pod_id=""
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
    cleanup_runpod() {
      delete_pod || true
      if [[ "$pod_create_failed" -eq 1 ]]; then
        delete_named_pods
      fi
    }
    trap cleanup_runpod EXIT
    [[ "$RTF_RUNPOD_MAX_HOURS" =~ ^[1-6]$ ]] || {
      echo 'RTF_RUNPOD_MAX_HOURS must be an integer between 1 and 6' >&2
      exit 2
    }
    terminate_after="$(date -u -d "+${RTF_RUNPOD_MAX_HOURS} hours" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || true)"
    if [[ -z "$terminate_after" ]]; then
      # BSD date (for local macOS execution) uses a different flag shape.
      terminate_after="$(date -u -v+${RTF_RUNPOD_MAX_HOURS}H '+%Y-%m-%dT%H:%M:%SZ')"
    fi
    [[ "$terminate_after" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || {
      echo "failed to generate RunPod termination deadline: $terminate_after" >&2
      exit 2
    }
    env_json="$(jq -cn \
      --arg run_id "$RTF_RUN_ID" --arg manifest "$RTF_MANIFEST" \
      --arg output "$RTF_OUTPUT" --arg model_id "$RTF_MODEL_ID" \
      --arg content_output "$RTF_CONTENT_OUTPUT" \
      --arg model_revision "$RTF_MODEL_REVISION" --arg dataset_id "$RTF_DATASET_ID" \
      --arg dataset_revision "$RTF_DATASET_REVISION" --arg gpu "$RTF_GPU" \
      --arg batch "$RTF_BATCH_SIZE" --arg precision "$RTF_PRECISION" \
      --arg decoder "$RTF_DECODER" --arg fixture_repo "$RTF_FIXTURE_REPO_ID" \
      --arg fixture_revision "$RTF_FIXTURE_REVISION" --arg hf_token "${HF_TOKEN:-}" \
      --arg result_repo "$RTF_RESULT_REPO_ID" --arg result_path "$RTF_RESULT_PATH" \
      --arg image_digest "$RTF_IMAGE_DIGEST" \
      --arg profile "$RTF_INSPECTION_PROFILE" --arg profile_id "$RTF_PROFILE_ID" \
      --arg config "$RTF_DATASET_CONFIGURATION" --arg split "$RTF_DATASET_SPLIT" --arg seed "$RTF_DATASET_SEED" \
      --arg count_min "$RTF_DATASET_COUNT_MIN" --arg count_max "$RTF_DATASET_COUNT_MAX" \
      --arg target_total "$RTF_DATASET_TARGET_TOTAL_SEC" --arg max_duration "$RTF_DATASET_MAX_DURATION_SEC" \
      --arg repeat "$RTF_REPEAT" --arg filename "$RTF_FIXTURE_FILENAME" --arg manifest_sha "$RTF_FIXTURE_MANIFEST_SHA256" \
      --arg cuda_diagnostics "${RTF_CUDA_DIAGNOSTICS:-0}" --arg num_workers "${RTF_NUM_WORKERS:-0}" \
      --arg error_log "/output/benchmark-error.log" \
      '{RTF_RUN_ID:$run_id,RTF_MANIFEST:$manifest,RTF_OUTPUT:$output,RTF_CONTENT_OUTPUT:$content_output,RTF_ERROR_LOG:$error_log,RTF_MODEL_ID:$model_id,RTF_MODEL_REVISION:$model_revision,RTF_DATASET_ID:$dataset_id,RTF_DATASET_REVISION:$dataset_revision,RTF_DATASET_CONFIGURATION:$config,RTF_DATASET_SPLIT:$split,RTF_DATASET_SEED:$seed,RTF_DATASET_COUNT_MIN:$count_min,RTF_DATASET_COUNT_MAX:$count_max,RTF_DATASET_TARGET_TOTAL_SEC:$target_total,RTF_DATASET_MAX_DURATION_SEC:$max_duration,RTF_INSPECTION_PROFILE:$profile,RTF_PROFILE_ID:$profile_id,RTF_GPU:$gpu,RTF_BATCH_SIZE:$batch,RTF_PRECISION:$precision,RTF_REPEAT:$repeat,RTF_DECODER:$decoder,RTF_FIXTURE_REPO_ID:$fixture_repo,RTF_FIXTURE_REVISION:$fixture_revision,RTF_FIXTURE_FILENAME:$filename,RTF_FIXTURE_MANIFEST_SHA256:$manifest_sha,RTF_CUDA_DIAGNOSTICS:$cuda_diagnostics,RTF_NUM_WORKERS:$num_workers,RTF_RESULT_REPO_ID:$result_repo,RTF_RESULT_PATH:$result_path,RTF_IMAGE_DIGEST:$image_digest,HF_TOKEN:$hf_token,RTF_PROVIDER:"cuda",RTF_SERVICE_ID:"runpod-pod"}')"
    set +e
    pod_json="$(runpodctl pod create --name "${RTF_RUN_ID}" --image "$IMAGE" \
      --cloud-type SECURE --gpu-id "$RUNPOD_GPU_ID" --env "$env_json" --docker-args 'sleep infinity' \
      --ports 22/tcp --wait --wait-timeout 30m --terminate-after "$terminate_after" \
      --output json 2>&1)"
    pod_create_status=$?
    set -e
    # `jq -e` prints JSON null before returning failure for an error response;
    # use `// empty` so the literal string "null" can never reach pod delete.
    pod_id="$(jq -er '(.id // .podId // .pod_id) // empty' <<<"$pod_json" 2>/dev/null || true)"
    if [[ "$pod_create_status" -ne 0 || -z "$pod_id" ]]; then
      pod_create_failed=1
      printf '%s\n' "$pod_json" >&2
      [[ "$pod_create_status" -ne 0 ]] && exit "$pod_create_status"
      echo 'RunPod pod create did not return a pod id' >&2
      exit 1
    fi
    ssh_command="$(runpodctl ssh info "$pod_id" --output json | jq -er '.sshCommand')"
    runpod_ssh() {
      local remote_command
      printf -v remote_command '%q ' "$@"
      eval "$ssh_command $remote_command"
    }
    # The Pod command intentionally keeps the container alive. Invoke the
    # image entrypoint explicitly over the supported SSH path so fixture
    # loading, inference, publishing, and result collection share one path.
    set +e
    runpod_ssh sh -c "export RTF_JOB_ID='$pod_id'; exec /opt/rtf-benchmark/entrypoint.sh"
    remote_status=$?
    set -e
    runpod_ssh cat "$RTF_CONTENT_OUTPUT" > "${RTF_LOCAL_CONTENT:-content.json}" || true
    runpod_ssh cat "$RTF_OUTPUT" > "${RTF_LOCAL_OUTPUT:-metrics.json}" || true
    runpod_ssh cat "${RTF_RECEIPT:-/output/result-receipt.json}" > "${RTF_LOCAL_RECEIPT:-result-receipt.json}" || true
    if [[ ! -s "${RTF_LOCAL_RECEIPT:-result-receipt.json}" ]]; then
      mkdir -p "$(dirname "${RTF_LOCAL_RECEIPT:-result-receipt.json}")"
      jq -n \
        --arg run_id "$RTF_RUN_ID" --arg error_message "RunPod execution did not produce a result receipt" \
        --arg model_id "$RTF_MODEL_ID" --arg model_revision "$RTF_MODEL_REVISION" \
        --arg dataset_id "$RTF_DATASET_ID" --arg dataset_revision "$RTF_DATASET_REVISION" \
        --arg image_digest "$RTF_IMAGE_DIGEST" --arg fixture_repo_id "$RTF_FIXTURE_REPO_ID" \
        --arg fixture_revision "$RTF_FIXTURE_REVISION" --arg manifest_sha256 "$RTF_FIXTURE_MANIFEST_SHA256" \
        --arg gpu "$RTF_GPU" --arg profile "$RTF_INSPECTION_PROFILE" --arg batch_size "$RTF_BATCH_SIZE" \
        '{schema_version:1,run_id:$run_id,status:"blocked",job_id:null,result_uri:null,result_sha256:null,metrics_uri:null,metrics_sha256:null,error_code:"PROVIDER_EXECUTION_FAILED",error_message:$error_message,model_id:$model_id,model_revision:$model_revision,dataset_id:$dataset_id,dataset_revision:$dataset_revision,image_digest:$image_digest,fixture_repo_id:$fixture_repo_id,fixture_revision:$fixture_revision,manifest_sha256:$manifest_sha256,provider:"cuda",environment:"linux",service_id:"runpod-pod",gpu:$gpu,inspection_profile:$profile,batch_size:($batch_size|tonumber)}' \
        > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
    fi
    [[ "$remote_status" -eq 0 ]] || exit "$remote_status"
    # Delete this Pod as soon as its metrics and receipt have been copied.
    # The EXIT trap remains as a failure-path safety net.
    delete_pod
    ;;
esac
