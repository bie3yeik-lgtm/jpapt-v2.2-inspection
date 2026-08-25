#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: run-runpod-execution-preflight.sh --phase {runner|remote} [options]

Runner phase (before Pod create):
  Validates credentials and billing metadata prerequisites on the Actions runner.

Remote phase (after SSH readiness, before benchmark):
  Validates GPU, CUDA, entrypoint, and output paths on the Pod, then exits non-zero
  when execution cannot continue.
EOF
  exit 2
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

phase=""
pod_id=""
gpu_id=""
min_cuda_version=""
ssh_command=""
pod_state_json=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase) phase="${2:?missing --phase value}"; shift 2 ;;
    --pod-id) pod_id="${2:?missing --pod-id value}"; shift 2 ;;
    --gpu-id) gpu_id="${2:?missing --gpu-id value}"; shift 2 ;;
    --min-cuda-version) min_cuda_version="${2:-}"; shift 2 ;;
    --ssh-command) ssh_command="${2:?missing --ssh-command value}"; shift 2 ;;
    --pod-state-json) pod_state_json="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

[[ "$phase" == runner || "$phase" == remote ]] || usage

log_check() {
  local check="$1"
  local status="$2"
  local detail="${3:-}"
  if [[ -n "$detail" ]]; then
    echo "RunPod execution preflight: phase=$phase check=$check status=$status detail=$detail" >&2
  else
    echo "RunPod execution preflight: phase=$phase check=$check status=$status" >&2
  fi
}

fail_preflight() {
  local code="$1"
  local message="$2"
  log_check summary fail "$code"
  printf 'RUNPOD_PREFLIGHT_FAILURE_CODE=%s\n' "$code"
  printf 'RUNPOD_PREFLIGHT_FAILURE_MESSAGE=%s\n' "$message"
  exit 1
}

compare_cuda_versions() {
  local observed="$1"
  local required="$2"
  local observed_major observed_minor required_major required_minor
  observed_major="${observed%%.*}"
  observed_minor="${observed##*.}"
  required_major="${required%%.*}"
  required_minor="${required##*.}"
  (( observed_major > required_major || (observed_major == required_major && observed_minor >= required_minor) ))
}

runner_preflight() {
  log_check start pass

  if [[ -n "${HF_TOKEN:-}" ]]; then
    log_check hf_token pass "present"
  else
    log_check hf_token fail "missing"
    fail_preflight RUNPOD_PREFLIGHT_HF_TOKEN_MISSING \
      "HF_TOKEN is required before RunPod execution for metrics upload and billing metadata enrichment"
  fi

  if [[ -f scripts/ci/enrich_runpod_job_metrics.py ]]; then
    log_check billing_collector_script pass
  else
    log_check billing_collector_script fail
    fail_preflight RUNPOD_PREFLIGHT_BILLING_SCRIPT_MISSING \
      "RunPod billing metadata collector is missing: scripts/ci/enrich_runpod_job_metrics.py"
  fi

  if mise exec -- uv run python -m py_compile scripts/ci/enrich_runpod_job_metrics.py >/dev/null 2>&1; then
    log_check billing_collector_compile pass
  else
    log_check billing_collector_compile fail
    fail_preflight RUNPOD_PREFLIGHT_BILLING_SCRIPT_INVALID \
      "RunPod billing metadata collector failed py_compile"
  fi

  if [[ "${RTF_RUNPOD_PREFLIGHT_SKIP_BILLING_PROBE:-0}" == 1 ]]; then
    log_check billing_api skip "RTF_RUNPOD_PREFLIGHT_SKIP_BILLING_PROBE=1"
  elif billing_probe_output="$(mise exec -- uv run python - <<'PY' 2>&1
import importlib.util
import sys
from pathlib import Path

module_path = Path("scripts/ci/enrich_runpod_job_metrics.py")
spec = importlib.util.spec_from_file_location("enrich_runpod_job_metrics", module_path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
token = module.resolve_runpod_token()
module.probe_billing_api(token)
print("ok")
PY
)"; then
    log_check billing_api pass
  else
    detail="$(tr '\r\n' '  ' <<<"$billing_probe_output" | cut -c1-500)"
    log_check billing_api fail "$detail"
    fail_preflight RUNPOD_PREFLIGHT_BILLING_API_UNAVAILABLE \
      "RunPod billing API probe failed before Pod create: $detail"
  fi

  log_check summary pass
}

remote_preflight() {
  [[ -n "$pod_id" && -n "$gpu_id" && -n "$ssh_command" ]] || usage
  log_check start pass "pod_id=$pod_id gpu_id=$gpu_id"

  if [[ -n "$pod_state_json" ]]; then
    pod_gpu_id="$(jq -er '(.gpu.id // .machine.gpuTypeId // .machine.gpu_type_id // empty)' \
      <<<"$pod_state_json" 2>/dev/null || true)"
    if [[ -z "$pod_gpu_id" ]]; then
      log_check pod_gpu_identity skip "pod get did not expose gpu.id or machine.gpuTypeId"
    elif [[ "$pod_gpu_id" == "$gpu_id" ]]; then
      log_check pod_gpu_identity pass "$pod_gpu_id"
    else
      log_check pod_gpu_identity fail "expected=$gpu_id observed=$pod_gpu_id"
      fail_preflight RUNPOD_PREFLIGHT_GPU_ID_MISMATCH \
        "RunPod Pod GPU identity mismatch: expected $gpu_id, pod get reported $pod_gpu_id"
    fi
  else
    log_check pod_gpu_identity skip "pod state unavailable"
  fi

  ssh_remote() {
    timeout 60s bash -c "$ssh_command $(printf '%q' "$1")" 2>&1
  }

  nvidia_smi_output="$(ssh_remote 'nvidia-smi && test -e /dev/nvidia0' || true)"
  if [[ -n "$nvidia_smi_output" ]] && grep -Fq 'CUDA Version:' <<<"$nvidia_smi_output"; then
    log_check nvidia_smi pass
  else
    detail="$(tr '\r\n' '  ' <<<"$nvidia_smi_output" | cut -c1-500)"
    log_check nvidia_smi fail "$detail"
    fail_preflight RUNPOD_PREFLIGHT_NVIDIA_SMI_FAILED \
      "nvidia-smi failed or /dev/nvidia0 is unavailable on the Pod"
  fi

  gpu_name_output="$(ssh_remote 'nvidia-smi --query-gpu=name --format=csv,noheader' || true)"
  gpu_name_output="$(sed -e 's/\r$//' -e 's/[[:space:]]\+$//' <<<"$gpu_name_output")"
  if [[ -n "$gpu_name_output" ]] && grep -Fx "$gpu_id" <<<"$gpu_name_output" >/dev/null; then
    log_check gpu_name pass "$gpu_name_output"
  else
    detail="$(tr '\r\n' '  ' <<<"$gpu_name_output" | cut -c1-200)"
    log_check gpu_name fail "expected=$gpu_id observed=$detail"
    fail_preflight RUNPOD_PREFLIGHT_GPU_NAME_MISMATCH \
      "Pod GPU name mismatch: expected $gpu_id, nvidia-smi reported ${detail:-<empty>}"
  fi

  if [[ -n "$min_cuda_version" ]]; then
    cuda_version="$(grep -Eo 'CUDA Version: [0-9]+\.[0-9]+' <<<"$nvidia_smi_output" | awk '{print $3}' | head -n 1 || true)"
    if [[ -n "$cuda_version" ]] && compare_cuda_versions "$cuda_version" "$min_cuda_version"; then
      log_check cuda_runtime pass "observed=$cuda_version required=$min_cuda_version"
    else
      log_check cuda_runtime fail "observed=${cuda_version:-unknown} required=$min_cuda_version"
      fail_preflight RUNPOD_PREFLIGHT_CUDA_REQUIREMENT_UNSATISFIED \
        "Pod CUDA runtime ${cuda_version:-unknown} is below required $min_cuda_version"
    fi
  else
    log_check cuda_runtime skip "min_cuda_version not configured"
  fi

  if ssh_remote 'test -x /opt/rtf-benchmark/entrypoint.sh' >/dev/null; then
    log_check entrypoint pass "/opt/rtf-benchmark/entrypoint.sh"
  else
    log_check entrypoint fail
    fail_preflight RUNPOD_PREFLIGHT_ENTRYPOINT_MISSING \
      "Benchmark entrypoint is missing or not executable: /opt/rtf-benchmark/entrypoint.sh"
  fi

  if ssh_remote 'test -d /output && test -w /output' >/dev/null; then
    log_check output_dir pass "/output"
  else
    log_check output_dir fail
    fail_preflight RUNPOD_PREFLIGHT_OUTPUT_DIR_UNAVAILABLE \
      "Pod output directory /output is missing or not writable"
  fi

  output_df="$(ssh_remote 'df -h /output | tail -n 1' || true)"
  if [[ -n "$output_df" ]]; then
    log_check output_disk pass "$(tr '\r\n' '  ' <<<"$output_df" | cut -c1-200)"
  else
    log_check output_disk skip "df unavailable"
  fi

  log_check summary pass "pod_id=$pod_id"
}

case "$phase" in
  runner) runner_preflight ;;
  remote) remote_preflight ;;
esac
