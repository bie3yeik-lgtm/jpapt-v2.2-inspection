#!/usr/bin/env bash
set -euo pipefail

test_dir="$(mktemp -d "${TMPDIR:-/tmp}/runpod-cuda-probe-test.XXXXXX")"
mock_bin="$test_dir/bin"
mkdir -p "$mock_bin"

cat > "$mock_bin/runpodctl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  *"gpu list"*) if [[ "${MOCK_UNAVAILABLE:-0}" == 1 ]]; then printf '%s\n' '[{"gpuId":"NVIDIA RTX A5000","available":false,"secureCloud":true,"communityCloud":false}]'; else printf '%s\n' '[{"gpuId":"NVIDIA RTX A5000","available":true,"secureCloud":true,"communityCloud":false}]'; fi ;;
  *"pod create"*)
    create_count=0
    if [[ -f "$MOCK_CREATE_COUNT_FILE" ]]; then create_count="$(<"$MOCK_CREATE_COUNT_FILE")"; fi
    create_count=$((create_count + 1)); printf '%s\n' "$create_count" > "$MOCK_CREATE_COUNT_FILE"
    if [[ "$create_count" -le "${MOCK_CREATE_CAPACITY_FAILURES:-0}" ]]; then
      printf '%s\n' '{"error":"There are no longer any instances available with the requested specifications."}'
      exit 1
    fi
    printf '%s\n' '{"id":"probe-pod-1"}' ;;
  *"pod get"*) printf '%s\n' '{"id":"probe-pod-1","desiredStatus":"RUNNING","runtimeStatus":"running"}' ;;
  *"pod list"*)
    create_count=0
    if [[ -f "$MOCK_CREATE_COUNT_FILE" ]]; then create_count="$(<"$MOCK_CREATE_COUNT_FILE")"; fi
    if [[ "$create_count" -le "${MOCK_CREATE_CAPACITY_FAILURES:-0}" ]]; then printf '%s\n' '[]'; else printf '%s\n' '[{"id":"probe-pod-1","desiredStatus":"RUNNING","runtimeStatus":"running"}]'; fi ;;
  *"ssh info"*) printf '%s\n' '{"sshCommand":"ssh mock-host"}' ;;
  *"pod delete"*) : > "$RUNPOD_DELETE_MARKER" ;;
  *) printf '%s\n' '[]' ;;
esac
MOCK
cat > "$mock_bin/ssh" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"nvidia-smi --query-gpu=name --format=csv,noheader"* ]]; then
  printf '%s\n' 'NVIDIA RTX A5000'
else
  # The table-form output may abbreviate the GPU name when the column is narrow.
  printf '%s\n' 'NVIDIA-SMI 580.00    Driver Version: 580.00    CUDA Version: 13.0' 'NVIDIA RTX A5000...'
fi
MOCK
chmod +x "$mock_bin/runpodctl" "$mock_bin/ssh"

export PATH="$mock_bin:$PATH"
export RUNPOD_TOKEN=test-token
export RUNPOD_DELETE_MARKER="$test_dir/deleted"
export MOCK_CREATE_COUNT_FILE="$test_dir/create-count"
report="$test_dir/pass.json"
bash scripts/ci/run-runpod-cuda-probe.sh \
  --gpu a5000 --gpu-id 'NVIDIA RTX A5000' --image 'ghcr.io/example/probe@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  --min-cuda-version 13.0 --output "$report"
jq -e '.status == "PASS" and .cleanup_status == "PASS" and .cuda_runtime_check == "PASS"' "$report" >/dev/null
test -e "$RUNPOD_DELETE_MARKER"

export MOCK_CREATE_CAPACITY_FAILURES=2
retry_report="$test_dir/retry.json"
bash scripts/ci/run-runpod-cuda-probe.sh \
  --gpu a5000 --gpu-id 'NVIDIA RTX A5000' --image 'ghcr.io/example/probe@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  --min-cuda-version 13.0 --output "$retry_report" --create-retry-backoff-seconds 1
jq -e '.status == "PASS" and .cleanup_status == "PASS"' "$retry_report" >/dev/null
[[ "$(<"$MOCK_CREATE_COUNT_FILE")" -eq 3 ]]

rm -f "$MOCK_CREATE_COUNT_FILE"
export MOCK_CREATE_CAPACITY_FAILURES=3
exhausted_report="$test_dir/exhausted.json"
if bash scripts/ci/run-runpod-cuda-probe.sh \
  --gpu a5000 --gpu-id 'NVIDIA RTX A5000' --image 'ghcr.io/example/probe@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  --min-cuda-version 13.0 --output "$exhausted_report" --create-retry-backoff-seconds 1; then
  echo 'capacity exhaustion unexpectedly passed' >&2
  exit 1
fi
jq -e '.failure_code == "RUNPOD_NO_INSTANCE_AVAILABLE" and .cleanup_status == "NOT_REQUIRED"' "$exhausted_report" >/dev/null

export MOCK_UNAVAILABLE=1
if bash scripts/ci/run-runpod-cuda-probe.sh \
  --gpu a5000 --gpu-id 'NVIDIA RTX A5000' --image 'ghcr.io/example/probe@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  --min-cuda-version 13.0 --output "$test_dir/fail.json"; then
  echo 'unavailable GPU unexpectedly passed' >&2
  exit 1
fi
jq -e '.failure_code == "RUNPOD_GPU_NOT_AVAILABLE" and .cleanup_status == "NOT_REQUIRED"' "$test_dir/fail.json" >/dev/null
echo 'RunPod CUDA probe fixture tests: PASS'
