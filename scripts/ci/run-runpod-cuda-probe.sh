#!/usr/bin/env bash
set -euo pipefail

usage() { echo "usage: $0 --gpu NAME --gpu-id ID --image IMAGE --min-cuda-version VERSION --output PATH [--cloud-type auto|SECURE|COMMUNITY] [--terminate-after-hours HOURS] [--heartbeat-seconds SECONDS] [--create-attempts N] [--create-retry-backoff-seconds SECONDS]" >&2; exit 2; }
gpu=""; gpu_id=""; image=""; min_cuda_version=""; output=""; cloud_type=auto; terminate_after_hours=24; heartbeat_seconds=30; create_attempts=3; create_retry_backoff_seconds=20
while (($#)); do
  case "$1" in
    --gpu) gpu="${2:?missing --gpu value}"; shift 2;;
    --gpu-id) gpu_id="${2:?missing --gpu-id value}"; shift 2;;
    --image) image="${2:?missing --image value}"; shift 2;;
    --min-cuda-version) min_cuda_version="${2:?missing --min-cuda-version value}"; shift 2;;
    --output) output="${2:?missing --output value}"; shift 2;;
    --cloud-type) cloud_type="${2:?missing --cloud-type value}"; shift 2;;
    --terminate-after-hours) terminate_after_hours="${2:?missing --terminate-after-hours value}"; shift 2;;
    --heartbeat-seconds) heartbeat_seconds="${2:?missing --heartbeat-seconds value}"; shift 2;;
    --create-attempts) create_attempts="${2:?missing --create-attempts value}"; shift 2;;
    --create-retry-backoff-seconds) create_retry_backoff_seconds="${2:?missing --create-retry-backoff-seconds value}"; shift 2;;
    *) usage;;
  esac
done
[[ -n "$gpu" && -n "$gpu_id" && -n "$image" && -n "$min_cuda_version" && -n "$output" ]] || usage
[[ "$min_cuda_version" =~ ^[0-9]+\.[0-9]+$ ]] || { echo 'minimum CUDA version must be major.minor' >&2; exit 2; }
[[ "$cloud_type" == auto || "$cloud_type" == SECURE || "$cloud_type" == COMMUNITY ]] || usage
[[ "$terminate_after_hours" =~ ^[1-9][0-9]*$ && "$terminate_after_hours" -le 168 ]] || { echo 'terminate-after-hours must be 1..168' >&2; exit 2; }
[[ "$heartbeat_seconds" =~ ^[1-9][0-9]*$ ]] || { echo 'heartbeat-seconds must be positive' >&2; exit 2; }
[[ "$create_attempts" =~ ^[1-9][0-9]*$ && "$create_attempts" -le 5 ]] || { echo 'create-attempts must be 1..5' >&2; exit 2; }
[[ "$create_retry_backoff_seconds" =~ ^[1-9][0-9]*$ && "$create_retry_backoff_seconds" -le 300 ]] || { echo 'create-retry-backoff-seconds must be 1..300' >&2; exit 2; }
command -v runpodctl >/dev/null || { echo 'runpodctl is required' >&2; exit 1; }
command -v jq >/dev/null || { echo 'jq is required' >&2; exit 1; }
[[ -n "${RUNPOD_TOKEN:-}" ]] || { echo 'RUNPOD_TOKEN is required' >&2; exit 1; }

mkdir -p "$(dirname "$output")"
run_id="rtf-cuda-probe-${gpu}-$(date -u +%Y%m%dT%H%M%SZ)-${GITHUB_RUN_ID:-local}"
pod_id=""; cleanup_status=not_started; probe_status=FAIL; failure_code=""; failure_message=""
cloud_type_observed="$cloud_type"; started_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

write_report() {
  jq -n --arg run_id "$run_id" --arg started_at "$started_at" --arg finished_at "$1" \
    --arg gpu "$gpu" --arg gpu_id "$gpu_id" --arg image "$image" --arg min_cuda "$min_cuda_version" \
    --arg cloud_type "$cloud_type_observed" --arg pod_id "$pod_id" --arg status "$probe_status" \
    --arg failure_code "$failure_code" --arg failure_message "$failure_message" --arg cleanup "$cleanup_status" \
    '{schema_version:1,run_id:$run_id,observed_at:$started_at,finished_at:$finished_at,service_id:"runpod-pod",provider:"cuda",environment:"linux",gpu:$gpu,gpu_id:$gpu_id,image:$image,minimum_cuda_version:$min_cuda,cloud_type:$cloud_type,pod_id:(if $pod_id=="" then null else $pod_id end),status:$status,cuda_scheduler_check:(if $status=="PASS" then "PASS" else "NOT_VERIFIED" end),cuda_runtime_check:(if $status=="PASS" then "PASS" else "NOT_VERIFIED" end),cuda_driver_check:(if $status=="PASS" then "PASS" else "NOT_VERIFIED" end),provider_execution_check:(if $status=="PASS" then "PASS" else "NOT_VERIFIED" end),failure_code:(if $failure_code=="" then null else $failure_code end),failure_message:(if $failure_message=="" then null else $failure_message end),cleanup_status:$cleanup}' > "$output"
}
cleanup() {
  if [[ -n "$pod_id" ]]; then
    if runpodctl pod delete "$pod_id" >/dev/null 2>&1; then cleanup_status=PASS; else cleanup_status=FAIL; probe_status=FAIL; failure_code=RUNPOD_CLEANUP_FAILED; failure_message="failed to delete probe Pod $pod_id"; fi
  else cleanup_status=NOT_REQUIRED; fi
  write_report "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}
trap cleanup EXIT
trap 'failure_code=RUNPOD_PROBE_INTERRUPTED; failure_message="probe interrupted"; exit 143' INT TERM HUP

inventory="$(runpodctl gpu list --include-unavailable --output json 2>&1)" || { probe_status=BLOCKED; failure_code=RUNPOD_EXTERNAL_API_FAILED; failure_message="RunPod GPU inventory failed"; write_report "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"; exit 1; }
match="$(jq -c --arg gpu_id "$gpu_id" '[.[] | select((.gpuId // .gpu_id) == $gpu_id)] | first // empty' <<<"$inventory")"
if [[ -z "$match" ]] || [[ "$(jq -r '.available // false' <<<"$match")" != true ]]; then failure_code=RUNPOD_GPU_NOT_AVAILABLE; failure_message="GPU is not currently available: $gpu_id"; write_report "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"; exit 1; fi
if [[ "$cloud_type" == auto ]]; then
  if [[ "$(jq -r '.secureCloud // .secure_cloud // false' <<<"$match")" == true ]]; then cloud_type_observed=SECURE
  elif [[ "$(jq -r '.communityCloud // .community_cloud // false' <<<"$match")" == true ]]; then cloud_type_observed=COMMUNITY
  else failure_code=RUNPOD_GPU_CLOUD_UNAVAILABLE; failure_message="GPU has no available cloud capacity: $gpu_id"; write_report "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"; exit 1; fi
elif [[ "$cloud_type" == SECURE && "$(jq -r '.secureCloud // .secure_cloud // false' <<<"$match")" != true ]]; then
  failure_code=RUNPOD_GPU_CLOUD_UNAVAILABLE; failure_message="GPU is not available on SECURE cloud: $gpu_id"; write_report "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"; exit 1
elif [[ "$cloud_type" == COMMUNITY && "$(jq -r '.communityCloud // .community_cloud // false' <<<"$match")" != true ]]; then
  failure_code=RUNPOD_GPU_CLOUD_UNAVAILABLE; failure_message="GPU is not available on COMMUNITY cloud: $gpu_id"; write_report "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"; exit 1
fi
terminate_after="$(date -u -d "+${terminate_after_hours} hours" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -v+${terminate_after_hours}H '+%Y-%m-%dT%H:%M:%SZ')"
create_probe_pod_once() {
  local attempt="$1"
  create_log="$(mktemp "${TMPDIR:-/tmp}/rtf-cuda-probe.XXXXXX")"
  create_deadline=$(( $(date +%s) + 1800 )); create_pid=""; create_status=124; pod_id=""
  pod_json=""
  echo "RunPod CUDA probe Pod create attempt=$attempt/$create_attempts" >&2
  runpodctl pod create --name "$run_id" --image "$image" --cloud-type "$cloud_type_observed" --gpu-id "$gpu_id" --ssh --ports 22/tcp --terminate-after "$terminate_after" --min-cuda-version "$min_cuda_version" --output json >"$create_log" 2>&1 &
  create_pid=$!
  while [[ "$(date +%s)" -lt "$create_deadline" ]]; do
    pod_json="$(<"$create_log")"
    pod_id="$(jq -er '(.id // .podId // .pod_id) // empty' <<<"$pod_json" 2>/dev/null || true)"
    if [[ -z "$pod_id" ]]; then pod_id="$(runpodctl pod list --all --name "$run_id" --output json 2>/dev/null | jq -er '.[0] | (.id // .podId // .pod_id) // empty' 2>/dev/null || true)"; fi
    if [[ -n "$pod_id" ]]; then kill "$create_pid" 2>/dev/null || true; create_status=0; break; fi
    if ! kill -0 "$create_pid" 2>/dev/null; then
      if wait "$create_pid"; then create_status=0; else create_status=$?; fi
      break
    fi
    echo "RunPod CUDA probe heartbeat phase=pod_create attempt=$attempt/$create_attempts" >&2
    sleep "$heartbeat_seconds"
  done
  if [[ -z "$pod_id" ]]; then wait "$create_pid" 2>/dev/null || create_status=$?; pod_json="$(<"$create_log")"; pod_id="$(runpodctl pod list --all --name "$run_id" --output json 2>/dev/null | jq -er '.[0] | (.id // .podId // .pod_id) // empty' 2>/dev/null || true)"; fi
  rm -f "$create_log"
  [[ "$create_status" -eq 0 && -n "$pod_id" ]]
}

pod_created=0
for create_attempt in $(seq 1 "$create_attempts"); do
  if create_probe_pod_once "$create_attempt"; then
    pod_created=1
    break
  fi
  if ! grep -Eqi 'no longer any instances available|no instances available|insufficient capacity' <<<"$pod_json" || [[ "$create_attempt" -ge "$create_attempts" ]]; then
    break
  fi
  retry_inventory="$(runpodctl gpu list --include-unavailable --output json 2>&1 || true)"
  retry_match="$(jq -c --arg gpu_id "$gpu_id" '[.[] | select((.gpuId // .gpu_id) == $gpu_id)] | first // empty' <<<"$retry_inventory" 2>/dev/null || true)"
  echo "RunPod CUDA probe capacity retry: next_attempt=$((create_attempt + 1))/$create_attempts inventory=$(tr '\r\n' ' ' <<<"$retry_match" | cut -c1-1000)" >&2
  sleep $((create_retry_backoff_seconds * create_attempt))
done

if [[ "$pod_created" -ne 1 ]]; then
  echo "::error::RunPod CUDA probe Pod create failed: exit_status=$create_status pod_id=${pod_id:-<none>}" >&2
  tr '\r\n' '  ' <<<"$pod_json" | cut -c1-2000 >&2 || true
  failure_code=RUNPOD_POD_CREATE_FAILED; failure_message="probe Pod creation failed"
  if grep -Eqi 'cuda|nvidia driver|driver version|unsupported cuda' <<<"$pod_json"; then failure_code=RUNPOD_CUDA_REQUIREMENT_UNSATISFIED; fi
  if grep -Eqi 'no instances available|insufficient capacity' <<<"$pod_json"; then failure_code=RUNPOD_NO_INSTANCE_AVAILABLE; fi
  exit 1
fi
ssh_command=""; readiness_deadline=$(( $(date +%s) + 3600 )); consecutive_missing=0
while [[ "$(date +%s)" -lt "$readiness_deadline" && -z "$ssh_command" ]]; do
  pod_state="$(timeout 30s runpodctl pod get "$pod_id" --output json 2>/dev/null || true)"
  pod_list="$(timeout 30s runpodctl pod list --all --name "$run_id" --output json 2>/dev/null || true)"
  pod_exists="$(jq -er --arg pod_id "$pod_id" '[.[] | select((.id // .podId // .pod_id) == $pod_id)] | length > 0' <<<"$pod_list" 2>/dev/null || echo false)"
  runtime_status="$(jq -r '(.runtimeStatus // .runtime_status // .runtime.status // .desiredStatus // .desired_status // "") | ascii_downcase' <<<"$pod_state" 2>/dev/null || true)"
  echo "RunPod CUDA probe heartbeat phase=readiness exists=$pod_exists status=${runtime_status:-unknown}" >&2
  if [[ "$pod_exists" != true && -n "$pod_list" ]]; then consecutive_missing=$((consecutive_missing + 1)); else consecutive_missing=0; fi
  if [[ "$consecutive_missing" -ge 3 || "$runtime_status" == exited || "$runtime_status" == terminated ]]; then failure_code=RUNPOD_POD_EXITED_BEFORE_READINESS; failure_message="probe Pod disappeared or exited before SSH readiness"; exit 1; fi
  if ssh_json="$(timeout 30s runpodctl ssh info "$pod_id" --output json 2>&1)"; then
    ssh_status=0
  else
    ssh_status=$?
  fi
  ssh_command="$(jq -er '(.sshCommand // .ssh_command) // empty' <<<"$ssh_json" 2>/dev/null || true)"
  echo "RunPod CUDA probe SSH poll: exit_status=$ssh_status command_present=$([[ -n "$ssh_command" ]] && echo true || echo false)" >&2
  (( ssh_status == 0 )) || { echo "RunPod CUDA probe ssh info response: $(tr '\r\n' '  ' <<<"$ssh_json" | cut -c1-2000)" >&2; }
  [[ -n "$ssh_command" ]] || sleep "$heartbeat_seconds"
done
if [[ -z "$ssh_command" ]]; then
  echo "::error::RunPod CUDA probe SSH readiness timed out after 3600 seconds for pod_id=$pod_id" >&2
  failure_code=RUNPOD_SSH_FAILED; failure_message="probe Pod did not expose SSH before timeout"; exit 1
fi
ssh_command="${ssh_command/ssh /ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 }"
probe_output="$(timeout 60s bash -c "$ssh_command 'nvidia-smi && test -e /dev/nvidia0'" 2>/dev/null || true)"
if [[ -z "$probe_output" ]] || ! grep -F "$gpu_id" <<<"$probe_output" >/dev/null; then
  echo "::error::RunPod CUDA probe nvidia-smi failed or reported an unexpected GPU: pod_id=$pod_id" >&2
  tr '\r\n' '  ' <<<"$probe_output" | cut -c1-2000 >&2 || true
  failure_code=RUNPOD_NVIDIA_SMI_FAILED; failure_message="nvidia-smi did not report the requested GPU"; exit 1
fi
cuda_version="$(grep -Eo 'CUDA Version: [0-9]+\.[0-9]+' <<<"$probe_output" | awk '{print $3}' | head -n 1 || true)"
if [[ -z "$cuda_version" ]]; then failure_code=RUNPOD_CUDA_RUNTIME_FAILED; failure_message="nvidia-smi did not report a CUDA version"; exit 1; fi
required_major="${min_cuda_version%%.*}"; required_minor="${min_cuda_version##*.}"
observed_major="${cuda_version%%.*}"; observed_minor="${cuda_version##*.}"
if (( observed_major < required_major || (observed_major == required_major && observed_minor < required_minor) )); then failure_code=RUNPOD_CUDA_REQUIREMENT_UNSATISFIED; failure_message="observed CUDA $cuda_version is below required $min_cuda_version"; exit 1; fi
probe_status=PASS; failure_code=""; failure_message=""; exit 0
