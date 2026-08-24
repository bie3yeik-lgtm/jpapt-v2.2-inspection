#!/usr/bin/env bash
set -euo pipefail

usage() { echo "usage: $0 --gpu NAME --gpu-id ID --image IMAGE --min-cuda-version VERSION --output PATH [--cloud-type auto|SECURE|COMMUNITY]" >&2; exit 2; }
gpu=""; gpu_id=""; image=""; min_cuda_version=""; output=""; cloud_type=auto
while (($#)); do
  case "$1" in
    --gpu) gpu="${2:?missing --gpu value}"; shift 2;;
    --gpu-id) gpu_id="${2:?missing --gpu-id value}"; shift 2;;
    --image) image="${2:?missing --image value}"; shift 2;;
    --min-cuda-version) min_cuda_version="${2:?missing --min-cuda-version value}"; shift 2;;
    --output) output="${2:?missing --output value}"; shift 2;;
    --cloud-type) cloud_type="${2:?missing --cloud-type value}"; shift 2;;
    *) usage;;
  esac
done
[[ -n "$gpu" && -n "$gpu_id" && -n "$image" && -n "$min_cuda_version" && -n "$output" ]] || usage
[[ "$min_cuda_version" =~ ^[0-9]+\.[0-9]+$ ]] || { echo 'minimum CUDA version must be major.minor' >&2; exit 2; }
[[ "$cloud_type" == auto || "$cloud_type" == SECURE || "$cloud_type" == COMMUNITY ]] || usage
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
terminate_after="$(date -u -d '+15 minutes' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -v+15M '+%Y-%m-%dT%H:%M:%SZ')"
create_log="$(mktemp "${TMPDIR:-/tmp}/rtf-cuda-probe.XXXXXX")"
set +e
runpodctl pod create --name "$run_id" --image "$image" --cloud-type "$cloud_type_observed" --gpu-id "$gpu_id" --ssh --ports 22/tcp --terminate-after "$terminate_after" --min-cuda-version "$min_cuda_version" --output json >"$create_log" 2>&1
create_status=$?; set -e
pod_json="$(<"$create_log")"; pod_id="$(jq -er '(.id // .podId // .pod_id) // empty' <<<"$pod_json" 2>/dev/null || true)"
if [[ -z "$pod_id" ]]; then
  pod_id="$(runpodctl pod list --all --name "$run_id" --output json 2>/dev/null | jq -er '.[0] | (.id // .podId // .pod_id) // empty' 2>/dev/null || true)"
fi
if [[ "$create_status" -ne 0 || -z "$pod_id" ]]; then
  failure_code=RUNPOD_POD_CREATE_FAILED; failure_message="probe Pod creation failed"
  if grep -Eqi 'cuda|nvidia driver|driver version|unsupported cuda' <<<"$pod_json"; then failure_code=RUNPOD_CUDA_REQUIREMENT_UNSATISFIED; fi
  if grep -Eqi 'no instances available|insufficient capacity' <<<"$pod_json"; then failure_code=RUNPOD_NO_INSTANCE_AVAILABLE; fi
  exit 1
fi
ssh_command=""; deadline=$(( $(date +%s) + 300 ))
while [[ "$(date +%s)" -lt "$deadline" && -z "$ssh_command" ]]; do ssh_json="$(runpodctl ssh info "$pod_id" --output json 2>/dev/null || true)"; ssh_command="$(jq -er '(.sshCommand // .ssh_command) // empty' <<<"$ssh_json" 2>/dev/null || true)"; [[ -n "$ssh_command" ]] || sleep 10; done
if [[ -z "$ssh_command" ]]; then failure_code=RUNPOD_SSH_FAILED; failure_message="probe Pod did not expose SSH before timeout"; exit 1; fi
ssh_command="${ssh_command/ssh /ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 }"
probe_output="$(timeout 60s bash -c "$ssh_command 'nvidia-smi && test -e /dev/nvidia0'" 2>/dev/null || true)"
if [[ -z "$probe_output" ]] || ! grep -F "$gpu_id" <<<"$probe_output" >/dev/null; then failure_code=RUNPOD_NVIDIA_SMI_FAILED; failure_message="nvidia-smi did not report the requested GPU"; exit 1; fi
cuda_version="$(grep -Eo 'CUDA Version: [0-9]+\.[0-9]+' <<<"$probe_output" | awk '{print $3}' | head -n 1 || true)"
if [[ -z "$cuda_version" ]]; then failure_code=RUNPOD_CUDA_RUNTIME_FAILED; failure_message="nvidia-smi did not report a CUDA version"; exit 1; fi
required_major="${min_cuda_version%%.*}"; required_minor="${min_cuda_version##*.}"
observed_major="${cuda_version%%.*}"; observed_minor="${cuda_version##*.}"
if (( observed_major < required_major || (observed_major == required_major && observed_minor < required_minor) )); then failure_code=RUNPOD_CUDA_REQUIREMENT_UNSATISFIED; failure_message="observed CUDA $cuda_version is below required $min_cuda_version"; exit 1; fi
probe_status=PASS; failure_code=""; failure_message=""; exit 0
