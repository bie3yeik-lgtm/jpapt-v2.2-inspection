#!/usr/bin/env bash
set -euo pipefail

# Local RTF provider adapter verification. The default mock mode never creates
# an HF Job or RunPod Pod; it verifies the exact shell/provider hand-off with
# fake CLIs and machine-readable receipts.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODE="mock"
PROVIDER="all"
IMAGE="${RTF_LOCAL_IMAGE:-parakeet-rtf-benchmark:local}"

usage() {
  cat >&2 <<'EOF'
usage: test-rtf-provider-adapters.sh [options]

options:
  --mode static|mock|docker|live   verification mode (default: mock)
  --provider hf|runpod|all         provider cases for mock/live (default: all)
  --image IMAGE                    local image name for docker mode
  --allow-external                 required by live mode; creates remote work
EOF
  exit 2
}

ALLOW_EXTERNAL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="${2:?missing mode}"; shift 2 ;;
    --provider) PROVIDER="${2:?missing provider}"; shift 2 ;;
    --image) IMAGE="${2:?missing image}"; shift 2 ;;
    --allow-external) ALLOW_EXTERNAL=1; shift ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

cd "$ROOT"

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  PYTHON_BIN=""
fi

fail() {
  echo "RTF adapter test: FAIL: $*" >&2
  exit 1
}

pass() {
  echo "RTF adapter test: PASS: $*"
}

static_checks() {
  command -v bash >/dev/null || fail "bash is required"
  [[ -n "$PYTHON_BIN" ]] || fail "python or python3 is required"
  command -v jq >/dev/null || fail "jq is required"
  bash -n scripts/run-benchmark.sh scripts/ci/rtf-runpod-safe-wrapper.sh docker/rtf-benchmark/entrypoint.sh scripts/ci/rtf-local-preflight.sh scripts/ci/rtf-local-env.sh
  "$PYTHON_BIN" -m py_compile docker/rtf-benchmark/benchmark-runner/benchmark_runner/*.py
  "$PYTHON_BIN" -m json.tool evaluation/schemas/rtf-provider-content.schema.json >/dev/null
  "$PYTHON_BIN" -m json.tool evaluation/schemas/rtf-service-result.schema.json >/dev/null
  "$PYTHON_BIN" -m json.tool evaluation/schemas/rtf-service-metrics.schema.json >/dev/null
  grep -F 'LABEL io.jpapt.ghcr.package="parakeet-rtf-benchmark"' docker/rtf-benchmark/Dockerfile >/dev/null
  grep -F 'LABEL io.jpapt.role="rtf-benchmark"' docker/rtf-benchmark/Dockerfile >/dev/null
  grep -F 'ENTRYPOINT ["/opt/rtf-benchmark/entrypoint.sh"]' docker/rtf-benchmark/Dockerfile >/dev/null
  grep -F 'CMD ["sleep", "infinity"]' docker/rtf-benchmark/Dockerfile >/dev/null
  grep -F 'openssh-server' docker/rtf-benchmark/Dockerfile >/dev/null
  grep -F '/usr/sbin/sshd' docker/rtf-benchmark/entrypoint.sh >/dev/null
  grep -F 'PUBLIC_KEY' docker/rtf-benchmark/entrypoint.sh >/dev/null
  grep -F 'authorized_keys' docker/rtf-benchmark/entrypoint.sh >/dev/null
  grep -F '/run/rtf-benchmark.env' docker/rtf-benchmark/entrypoint.sh >/dev/null
  grep -F 'PubkeyAuthentication yes' docker/rtf-benchmark/entrypoint.sh >/dev/null
  grep -F 'python -m benchmark_runner.content_probe' docker/rtf-benchmark/entrypoint.sh >/dev/null
  grep -F 'hf jobs run --name "$RTF_RUN_ID"' scripts/run-benchmark.sh >/dev/null
  grep -F 'runpodctl pod create' scripts/run-benchmark.sh >/dev/null
  ! grep -F -- '--env "$env_json"' scripts/run-benchmark.sh >/dev/null
  grep -F 'runpodctl ssh info' scripts/run-benchmark.sh >/dev/null
  grep -F '/run/rtf-benchmark.env' scripts/run-benchmark.sh >/dev/null
  grep -F 'write_runpod_environment' scripts/run-benchmark.sh >/dev/null
  grep -F 'BatchMode=yes' scripts/run-benchmark.sh >/dev/null
  grep -F 'StrictHostKeyChecking=no' scripts/run-benchmark.sh >/dev/null
  grep -F 'UserKnownHostsFile=/dev/null' scripts/run-benchmark.sh >/dev/null
  ! grep -F 'lough inspection' scripts/run-benchmark.sh .github/workflows/ghcr-build-publish.yml .github/workflows/rtf-benchmark-run.yml >/dev/null
  ! grep -F 'RTF_NUM_WORKERS' scripts/run-benchmark.sh >/dev/null
  grep -F 'RTF_DATALOADER_POLICY=' docker/rtf-benchmark/benchmark-runner/benchmark_runner/transcribe_compat.py >/dev/null
  grep -F 'PROVIDER_CUDA_ILLEGAL_ACCESS' scripts/run-benchmark.sh >/dev/null
  grep -F 'RUNPOD_POD_CREATE_TIMEOUT' scripts/run-benchmark.sh >/dev/null
  grep -F 'RUNPOD_ACCOUNT_BALANCE_TOO_LOW' scripts/run-benchmark.sh >/dev/null
  grep -F 'RTF_RUNPOD_WAIT_TIMEOUT_MINUTES:=30' scripts/run-benchmark.sh >/dev/null
  grep -F 'RTF_RUNPOD_SSH_INFO_WAIT_MINUTES:=5' scripts/run-benchmark.sh >/dev/null
  grep -F 'RUNPOD_SSH_INFO_UNAVAILABLE' scripts/run-benchmark.sh >/dev/null
  grep -F 'ssh_info_diagnostic' scripts/run-benchmark.sh >/dev/null
  grep -F 'exact run' scripts/ci/rtf-runpod-safe-wrapper.sh >/dev/null
  grep -F 'phase=pod_create' scripts/run-benchmark.sh >/dev/null
  grep -F 'batch_sizes=(1)' .github/workflows/rtf-benchmark-run.yml >/dev/null
  grep -F 'batch_sizes=(1 8 32)' .github/workflows/rtf-benchmark-run.yml >/dev/null
  grep -F "inputs.cost_mode }}' == full-matrix" .github/workflows/rtf-benchmark-run.yml >/dev/null
  grep -F 'receipts="$(for batch_size in "${batch_sizes[@]}"' .github/workflows/rtf-benchmark-run.yml >/dev/null
  ! grep -F 'receipts="$(for batch_size in 1 8 32' .github/workflows/rtf-benchmark-run.yml >/dev/null
  grep -F 'RUNPOD_API' scripts/run-benchmark.sh scripts/ci/rtf-local-preflight.sh >/dev/null
  grep -F 'HF_TOKEN|RUNPOD_TOKEN|RUNPOD_API|HF_FLAVOR|RUNPOD_GPU_ID|RTF_*' scripts/ci/rtf-local-env.sh >/dev/null
  grep -F 'unset GITHUB_PAT_TOKEN GITHUB_CLASSIC_TOKEN GITHUB_TOKEN GH_TOKEN CR_PAT' scripts/ci/rtf-local-env.sh >/dev/null
  pass "Dockerfile, entrypoint, schemas, and provider adapter syntax"
}

write_fake_cli() {
  local fake_bin="$1"
  mkdir -p "$fake_bin"
  cat > "$fake_bin/hf" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == jobs && "${2:-}" == run ]]; then
  if [[ "${RTF_FAKE_FAILURE:-0}" == 1 ]]; then
    echo 'CUDA error: an illegal memory access was encountered' >&2
    exit 134
  fi
  echo 'RTF_CONTENT_PROBE={"schema_version":1,"run_id":"local-hf-test","status":"completed","content_available":true,"hypothesis_text":"mock"}'
  echo 'RTF_RESULT_RECEIPT={"schema_version":1,"run_id":"local-hf-test","status":"completed","job_id":"hf-mock-job","result_uri":"https://example.invalid/result","result_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","metrics_uri":"https://example.invalid/result","metrics_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
  exit 0
fi
echo "unsupported fake hf invocation" >&2
exit 2
EOF
  cat > "$fake_bin/runpodctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
  case "${1:-}:${2:-}" in
  pod:create)
    if [[ "${RTF_FAKE_RUNPOD_HANG:-0}" == 1 ]]; then
      sleep 120
    fi
    if [[ "${RTF_FAKE_RUNPOD_BALANCE_LOW:-0}" == 1 ]]; then
      printf '%s\n' '{"error":"failed to create pod: graphql error: Your account balance is too low to rent a pod. Please add funds to your account.","code":"graphql_error"}'
      exit 1
    fi
    if [[ "${RTF_FAKE_RUNPOD_FAILURE:-0}" == 1 ]]; then
      printf '%s\n' '{"error":"failed to create pod: graphql error: There are no longer any instances available with the requested specifications."}'
      exit 1
    fi
    printf '%s\n' '{"id":"runpod-mock-pod"}' ;;
  pod:get)
    if [[ "${RTF_FAKE_RUNPOD_NOT_READY:-0}" == 1 || "${RTF_FAKE_RUNPOD_GET_NOT_READY:-0}" == 1 ]]; then
      printf '%s\n' '{"id":"runpod-mock-pod","desiredStatus":"RUNNING","runtime":null}' ;
    else
      printf '%s\n' '{"id":"runpod-mock-pod","desiredStatus":"RUNNING","runtime":{}}' ;
    fi ;;
  pod:delete) : ;;
  pod:list)
    if [[ "${RTF_FAKE_RUNPOD_LIST_READY:-0}" == 1 && \
          "${RTF_FAKE_RUNPOD_FAILURE:-0}" != 1 && \
          "${RTF_FAKE_RUNPOD_BALANCE_LOW:-0}" != 1 && \
          "${RTF_FAKE_RUNPOD_HANG:-0}" != 1 ]]; then
      printf '%s\n' '[{"id":"runpod-mock-pod","runtimeStatus":"RUNNING"}]'
    else
      printf '%s\n' '[]'
    fi ;;
  ssh:info)
    if [[ "${RTF_FAKE_RUNPOD_SSH_INFO_FAILURE:-0}" == 1 ]]; then
      printf '%s\n' '{"code":"pod_not_ready","message":"pod not ready"}'
    else
      printf '%s\n' '{"ssh_command":"ssh mock@runpod"}'
    fi ;;
  *) echo "unsupported fake runpodctl invocation" >&2; exit 2 ;;
esac
EOF
  cat > "$fake_bin/ssh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${RTF_FAKE_RUNPOD_SSH_NOT_READY:-0}" == 1 && " $* " == *' true '* ]]; then
  exit 255
fi
if [[ "${RTF_FAKE_RUNPOD_REQUIRE_CI_OPTIONS:-0}" == 1 ]]; then
  [[ " $* " == *'BatchMode=yes'* ]] || exit 97
  [[ " $* " == *'StrictHostKeyChecking=no'* ]] || exit 98
  [[ " $* " == *'UserKnownHostsFile=/dev/null'* ]] || exit 99
fi
case " $* " in
  *' /output/content.json '*)
    printf '%s\n' '{"schema_version":1,"run_id":"local-runpod-test","status":"completed","content_available":true,"hypothesis_text":"mock"}' ;;
  *' /output/metrics.json '*)
    printf '%s\n' '{"schema_version":1,"run_id":"local-runpod-test","status":"completed"}' ;;
  *' /output/result-receipt.json '*)
    printf '%s\n' '{"schema_version":1,"run_id":"local-runpod-test","status":"completed","job_id":"runpod-mock-pod","result_uri":"https://example.invalid/result","result_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","metrics_uri":"https://example.invalid/result","metrics_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' ;;
  *) : ;;
esac
EOF
  chmod +x "$fake_bin/hf" "$fake_bin/runpodctl" "$fake_bin/ssh"
}

assert_result_files() {
  local case_dir="$1" expected_job="$2" expected_run_id="$3"
  [[ -s "$case_dir/content.json" ]] || fail "$expected_job content artifact was not collected"
  [[ -s "$case_dir/result-receipt.json" ]] || fail "$expected_job receipt was not collected"
  jq -e --arg run_id "$expected_run_id" \
    '.schema_version == 1 and .status == "completed" and .run_id == $run_id and .content_available == true' \
    "$case_dir/content.json" >/dev/null || fail "$expected_job content identity is invalid"
  jq -e --arg run_id "$expected_run_id" \
    '.schema_version == 1 and .status == "completed" and .run_id == $run_id' \
    "$case_dir/result-receipt.json" >/dev/null || fail "$expected_job receipt identity is invalid"
  pass "$expected_job mock content and receipt collection"
}

mock_case() {
  local provider="$1" fake_root case_dir run_id
  fake_root="$(mktemp -d)"
  case_dir="$fake_root/result"
  mkdir -p "$case_dir"
  run_id="local-${provider}-test"
  write_fake_cli "$fake_root/bin"
  export PATH="$fake_root/bin:$PATH"
  export RTF_RUN_ID="$run_id"
  export RTF_MODEL_ID="nvidia/parakeet-tdt_ctc-0.6b-ja"
  export RTF_MODEL_REVISION="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  export RTF_DATASET_ID="japanese-asr/ja_asr.common_voice_8_0"
  export RTF_DATASET_REVISION="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  export RTF_FIXTURE_REPO_ID="gawohok7/rtf-benchmark-fixtures"
  export RTF_FIXTURE_REVISION="cccccccccccccccccccccccccccccccccccccccc"
  export RTF_FIXTURE_MANIFEST_SHA256="dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  export RTF_IMAGE_DIGEST="sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
  export RTF_RESULT_REPO_ID="gawohok7/rtf-benchmark-fixtures"
  export RTF_RESULT_PATH="results/${run_id}/metrics.json"
  if [[ "$provider" == hf ]]; then
    export RTF_GPU=t4
  else
    export RTF_GPU=a5000
    # Exercise the current runpodctl list response, which reports
    # runtimeStatus rather than the pod-get runtime object.
    export RTF_FAKE_RUNPOD_LIST_READY=1
    export RTF_FAKE_RUNPOD_GET_NOT_READY=1
    export RTF_FAKE_RUNPOD_SSH_NOT_READY=0
  fi
  export RTF_BATCH_SIZE=1
  export RTF_PRECISION=float16
  export RTF_DECODER=tdt
  export RTF_REPEAT=1
  export RTF_INSPECTION_PROFILE="smoke"
  export HF_TOKEN=local-mock-token
  export RTF_LOCAL_CONTENT="$case_dir/content.json"
  export RTF_LOCAL_RECEIPT="$case_dir/result-receipt.json"
  export RTF_LOCAL_OUTPUT="$case_dir/metrics.json"
  export RTF_HF_LOG="$case_dir/hf-job.log"
  export RTF_RUNPOD_POLL_SECONDS=1
  export RTF_FAKE_RUNPOD_REQUIRE_CI_OPTIONS=1
  set +e
  if [[ "$provider" == hf ]]; then
    ./scripts/run-benchmark.sh --provider hf --image "ghcr.io/example/rtf@${RTF_IMAGE_DIGEST}" >/dev/null
  else
    ./scripts/run-benchmark.sh --provider runpod --image "ghcr.io/example/rtf@${RTF_IMAGE_DIGEST}" >/dev/null
  fi
  local status=$?
  set -e
  if [[ "${RTF_FAKE_RUNPOD_FAILURE:-0}" == 1 && "$provider" == runpod ]]; then
    [[ "$status" -ne 0 ]] || fail "RunPod no-instance mock unexpectedly succeeded"
    jq -e '.status == "blocked" and .error_code == "RUNPOD_NO_INSTANCE_AVAILABLE" and .run_id == $run_id' \
      --arg run_id "$run_id" "$case_dir/result-receipt.json" >/dev/null || fail "RunPod no-instance receipt was not classified"
    unset RTF_FAKE_RUNPOD_LIST_READY RTF_FAKE_RUNPOD_GET_NOT_READY RTF_FAKE_RUNPOD_SSH_NOT_READY RTF_FAKE_RUNPOD_REQUIRE_CI_OPTIONS
    rm -rf "$fake_root"
    pass "RunPod no-instance failure produces a typed receipt"
    return
  fi
  if [[ "${RTF_FAKE_RUNPOD_BALANCE_LOW:-0}" == 1 && "$provider" == runpod ]]; then
    [[ "$status" -ne 0 ]] || fail "RunPod balance-low mock unexpectedly succeeded"
    jq -e '.status == "blocked" and .error_code == "RUNPOD_ACCOUNT_BALANCE_TOO_LOW" and .run_id == $run_id' \
      --arg run_id "$run_id" "$case_dir/result-receipt.json" >/dev/null || fail "RunPod balance-low receipt was not classified"
    unset RTF_FAKE_RUNPOD_LIST_READY RTF_FAKE_RUNPOD_GET_NOT_READY RTF_FAKE_RUNPOD_SSH_NOT_READY RTF_FAKE_RUNPOD_REQUIRE_CI_OPTIONS RTF_FAKE_RUNPOD_BALANCE_LOW
    rm -rf "$fake_root"
    pass "RunPod account balance block produces a typed receipt"
    return
  fi
  [[ "$status" -eq 0 ]] || fail "$provider mock unexpectedly failed"
  assert_result_files "$case_dir" "$provider" "$run_id"
  unset RTF_FAKE_RUNPOD_LIST_READY RTF_FAKE_RUNPOD_GET_NOT_READY RTF_FAKE_RUNPOD_SSH_NOT_READY RTF_FAKE_RUNPOD_REQUIRE_CI_OPTIONS
  rm -rf "$fake_root"
}

mock_checks() {
  case "$PROVIDER" in
    all) mock_case hf; mock_case runpod; RTF_FAKE_RUNPOD_FAILURE=1 mock_case runpod; RTF_FAKE_RUNPOD_BALANCE_LOW=1 mock_case runpod; failure_receipt_check; runpod_create_timeout_check; runpod_ssh_info_failure_check ;;
    hf) mock_case hf; failure_receipt_check ;;
    runpod) mock_case runpod; RTF_FAKE_RUNPOD_FAILURE=1 mock_case runpod; RTF_FAKE_RUNPOD_BALANCE_LOW=1 mock_case runpod; runpod_create_timeout_check; runpod_ssh_info_failure_check ;;
    *) fail "unsupported provider: $PROVIDER" ;;
  esac
}

failure_receipt_check() {
  local fake_root case_dir status
  fake_root="$(mktemp -d)"
  case_dir="$fake_root/result"
  mkdir -p "$case_dir"
  write_fake_cli "$fake_root/bin"
  export PATH="$fake_root/bin:$PATH"
  export RTF_FAKE_FAILURE=1
  export RTF_RUN_ID="local-hf-failure-test" RTF_GPU=t4 RTF_BATCH_SIZE=1 RTF_INSPECTION_PROFILE=smoke
  export RTF_LOCAL_CONTENT="$case_dir/content.json"
  export RTF_LOCAL_RECEIPT="$case_dir/result-receipt.json"
  export RTF_LOCAL_OUTPUT="$case_dir/metrics.json"
  export RTF_HF_LOG="$case_dir/hf-job.log"
  set +e
  ./scripts/run-benchmark.sh --provider hf --image "ghcr.io/example/rtf@sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee" >/dev/null 2>&1
  status=$?
  set -e
  [[ "$status" -ne 0 ]] || fail "HF failure mock unexpectedly succeeded"
  jq -e '.status == "blocked" and .error_code == "PROVIDER_CUDA_ILLEGAL_ACCESS" and .run_id == "local-hf-failure-test"' \
    "$case_dir/result-receipt.json" >/dev/null || fail "CUDA failure receipt was not classified"
  unset RTF_FAKE_FAILURE
  rm -rf "$fake_root"
  pass "HF CUDA illegal access produces a typed failure receipt"
}

runpod_create_timeout_check() {
  local fake_root case_dir date_state status
  fake_root="$(mktemp -d)"
  case_dir="$fake_root/result"
  date_state="$fake_root/date-count"
  mkdir -p "$case_dir"
  write_fake_cli "$fake_root/bin"
  # Make the next epoch read exceed the one-minute production timeout without
  # waiting a real minute.
  cat > "$fake_root/bin/date" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ "\$*" == "+%s" ]]; then
  if [[ ! -f "$date_state" ]]; then
    touch "$date_state"
    echo 1000
  else
    echo 2000
  fi
else
  /usr/bin/date "\$@"
fi
EOF
  chmod +x "$fake_root/bin/date"
  export PATH="$fake_root/bin:$PATH"
  export RTF_FAKE_RUNPOD_HANG=1
  export RTF_RUN_ID="local-runpod-create-timeout-test" RTF_GPU=a5000 RTF_BATCH_SIZE=1 RTF_INSPECTION_PROFILE=smoke
  export RTF_MODEL_ID="nvidia/parakeet-tdt_ctc-0.6b-ja" RTF_MODEL_REVISION="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  export RTF_DATASET_ID="japanese-asr/ja_asr.common_voice_8_0" RTF_DATASET_REVISION="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  export RTF_FIXTURE_REPO_ID="gawohok7/rtf-benchmark-fixtures" RTF_FIXTURE_REVISION="cccccccccccccccccccccccccccccccccccccccc"
  export RTF_FIXTURE_MANIFEST_SHA256="dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  export RTF_IMAGE_DIGEST="sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
  export RTF_RUNPOD_CREATE_TIMEOUT_MINUTES=1 RTF_RUNPOD_POLL_SECONDS=1
  export RTF_LOCAL_RECEIPT="$case_dir/result-receipt.json"
  set +e
  ./scripts/run-benchmark.sh --provider runpod --image "ghcr.io/example/rtf@${RTF_IMAGE_DIGEST}" >"$case_dir/log" 2>&1
  status=$?
  set -e
  [[ "$status" -eq 124 ]] || fail "RunPod create timeout mock returned status $status"
  jq -e '.status == "blocked" and .error_code == "RUNPOD_POD_CREATE_TIMEOUT" and .run_id == "local-runpod-create-timeout-test"' \
    "$case_dir/result-receipt.json" >/dev/null || fail "RunPod create timeout receipt was not classified"
  unset RTF_FAKE_RUNPOD_HANG
  rm -rf "$fake_root"
  pass "RunPod Pod create timeout produces a typed receipt without external resources"
}

runpod_ssh_info_failure_check() {
  local fake_root case_dir date_state status
  fake_root="$(mktemp -d)"
  case_dir="$fake_root/result"
  date_state="$fake_root/date-count"
  mkdir -p "$case_dir"
  write_fake_cli "$fake_root/bin"
  cat > "$fake_root/bin/date" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ "\$*" == "+%s" ]]; then
  count=0
  [[ -f "$date_state" ]] && count="\$(cat "$date_state")"
  count=\$((count + 1))
  echo "\$count" > "$date_state"
  if (( \$count <= 4 )); then echo 1000; else echo 2000; fi
else
  /usr/bin/date "\$@"
fi
EOF
  chmod +x "$fake_root/bin/date"
  export PATH="$fake_root/bin:$PATH"
  export RTF_FAKE_RUNPOD_LIST_READY=1 RTF_FAKE_RUNPOD_SSH_INFO_FAILURE=1
  export RTF_RUN_ID="local-runpod-ssh-info-test" RTF_GPU=a5000 RTF_BATCH_SIZE=1 RTF_INSPECTION_PROFILE=smoke
  export RTF_MODEL_ID="nvidia/parakeet-tdt_ctc-0.6b-ja" RTF_MODEL_REVISION="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  export RTF_DATASET_ID="japanese-asr/ja_asr.common_voice_8_0" RTF_DATASET_REVISION="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  export RTF_FIXTURE_REPO_ID="gawohok7/rtf-benchmark-fixtures" RTF_FIXTURE_REVISION="cccccccccccccccccccccccccccccccccccccccc"
  export RTF_FIXTURE_MANIFEST_SHA256="dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  export RTF_IMAGE_DIGEST="sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
  export RTF_RUNPOD_SSH_INFO_WAIT_MINUTES=1 RTF_RUNPOD_POLL_SECONDS=1
  export RTF_LOCAL_RECEIPT="$case_dir/result-receipt.json"
  set +e
  ./scripts/run-benchmark.sh --provider runpod --image "ghcr.io/example/rtf@${RTF_IMAGE_DIGEST}" >"$case_dir/log" 2>&1
  status=$?
  set -e
  [[ "$status" -ne 0 ]] || fail "RunPod SSH info failure mock unexpectedly succeeded"
  jq -e '.status == "blocked" and .error_code == "RUNPOD_SSH_INFO_UNAVAILABLE" and (.error_message | contains("pod_not_ready"))' \
    "$case_dir/result-receipt.json" >/dev/null || fail "RunPod SSH info diagnostic receipt was not classified"
  unset RTF_FAKE_RUNPOD_LIST_READY RTF_FAKE_RUNPOD_SSH_INFO_FAILURE
  rm -rf "$fake_root"
  pass "RunPod SSH info failure produces a bounded diagnostic receipt"
}

docker_checks() {
  command -v docker >/dev/null || fail "docker is required for --mode docker"
  docker build --pull=false --tag "$IMAGE" \
    --build-arg SOURCE_REVISION=local-test \
    --build-arg RUNNER_VERSION=rtf-benchmark-local-test \
    --file docker/rtf-benchmark/Dockerfile .
  pass "RTF benchmark Dockerfile builds as $IMAGE"
}

live_checks() {
  [[ "$ALLOW_EXTERNAL" == 1 ]] || fail "--mode live requires --allow-external"
  [[ "$PROVIDER" == hf || "$PROVIDER" == runpod ]] || fail "live mode requires --provider hf or runpod"
  [[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required for live provider verification"
  if [[ "$PROVIDER" == runpod ]]; then
    [[ -n "${RUNPOD_TOKEN:-}" ]] || fail "RUNPOD_TOKEN is required for live RunPod verification"
  fi
  : "${RTF_RUN_ID:=local-live-${PROVIDER}-$(date -u +%Y%m%dT%H%M%SZ)}"
  : "${RTF_GPU:=$([[ "$PROVIDER" == hf ]] && echo t4 || echo a5000)}"
  : "${RTF_BATCH_SIZE:=1}"
  : "${RTF_IMAGE_DIGEST:?RTF_IMAGE_DIGEST must be set to a digest-pinned image}"
  [[ "$RTF_IMAGE_DIGEST" =~ ^sha256:[0-9a-fA-F]{64}$ ]] || fail "RTF_IMAGE_DIGEST is not a SHA-256 digest"
  if [[ "$PROVIDER" == runpod ]]; then
    ./scripts/ci/rtf-runpod-safe-wrapper.sh --provider runpod --image "ghcr.io/bie3yeik-lgtm/parakeet-rtf-benchmark@${RTF_IMAGE_DIGEST}"
  else
    ./scripts/run-benchmark.sh --provider hf --image "ghcr.io/bie3yeik-lgtm/parakeet-rtf-benchmark@${RTF_IMAGE_DIGEST}"
  fi
  receipt_path="${RTF_LOCAL_RECEIPT:-result-receipt.json}"
  [[ -s "$receipt_path" ]] || fail "live $PROVIDER provider produced no result receipt"
  jq -e '.status == "completed"' "$receipt_path" >/dev/null || {
    error_code="$(jq -r '.error_code // "PROVIDER_EXECUTION_FAILED"' "$receipt_path")"
    fail "live $PROVIDER provider produced a non-completed receipt: $error_code"
  }
  jq -e '
    (.metrics_sha256 | type == "string" and test("^[0-9a-fA-F]{64}$")) and
    (.result_sha256 | type == "string" and test("^[0-9a-fA-F]{64}$")) and
    (.metrics_uri | type == "string" and length > 0) and
    (.result_uri | type == "string" and length > 0)
  ' "$receipt_path" >/dev/null || fail "live $PROVIDER provider completed without metrics/result identity"
  pass "live $PROVIDER provider verification completed; external resources were used"
}

case "$MODE" in
  static) static_checks ;;
  mock) static_checks; mock_checks ;;
  docker) static_checks; docker_checks ;;
  live) static_checks; live_checks ;;
  *) fail "unsupported mode: $MODE" ;;
esac
