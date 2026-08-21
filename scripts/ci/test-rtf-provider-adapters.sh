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
  bash -n scripts/run-benchmark.sh docker/rtf-benchmark/entrypoint.sh
  "$PYTHON_BIN" -m py_compile docker/rtf-benchmark/benchmark-runner/benchmark_runner/*.py
  "$PYTHON_BIN" -m json.tool evaluation/schemas/rtf-provider-content.schema.json >/dev/null
  "$PYTHON_BIN" -m json.tool evaluation/schemas/rtf-service-result.schema.json >/dev/null
  "$PYTHON_BIN" -m json.tool evaluation/schemas/rtf-service-metrics.schema.json >/dev/null
  grep -F 'LABEL io.jpapt.ghcr.package="parakeet-rtf-benchmark"' docker/rtf-benchmark/Dockerfile >/dev/null
  grep -F 'LABEL io.jpapt.role="rtf-benchmark"' docker/rtf-benchmark/Dockerfile >/dev/null
  grep -F 'ENTRYPOINT ["/opt/rtf-benchmark/entrypoint.sh"]' docker/rtf-benchmark/Dockerfile >/dev/null
  grep -F 'python -m benchmark_runner.content_probe' docker/rtf-benchmark/entrypoint.sh >/dev/null
  grep -F 'hf jobs run --name "$RTF_RUN_ID"' scripts/run-benchmark.sh >/dev/null
  grep -F 'runpodctl pod create' scripts/run-benchmark.sh >/dev/null
  grep -F 'runpodctl ssh info' scripts/run-benchmark.sh >/dev/null
  ! grep -F 'lough inspection' scripts/run-benchmark.sh .github/workflows/ghcr-build-publish.yml .github/workflows/rtf-benchmark-run.yml >/dev/null
  ! grep -F 'RTF_NUM_WORKERS' scripts/run-benchmark.sh >/dev/null
  grep -F 'RTF_DATALOADER_POLICY=' docker/rtf-benchmark/benchmark-runner/benchmark_runner/transcribe_compat.py >/dev/null
  grep -F 'PROVIDER_CUDA_ILLEGAL_ACCESS' scripts/run-benchmark.sh >/dev/null
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
  pod:create) printf '%s\n' '{"id":"runpod-mock-pod"}' ;;
  pod:delete) : ;;
  pod:list) printf '%s\n' '[]' ;;
  ssh:info) printf '%s\n' '{"sshCommand":"ssh mock@runpod"}' ;;
  *) echo "unsupported fake runpodctl invocation" >&2; exit 2 ;;
esac
EOF
  cat > "$fake_bin/ssh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
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
  if [[ "$provider" == hf ]]; then
    ./scripts/run-benchmark.sh --provider hf --image "ghcr.io/example/rtf@${RTF_IMAGE_DIGEST}" >/dev/null
  else
    ./scripts/run-benchmark.sh --provider runpod --image "ghcr.io/example/rtf@${RTF_IMAGE_DIGEST}" >/dev/null
  fi
  assert_result_files "$case_dir" "$provider" "$run_id"
  rm -rf "$fake_root"
}

mock_checks() {
  case "$PROVIDER" in
    all) mock_case hf; mock_case runpod; failure_receipt_check ;;
    hf) mock_case hf; failure_receipt_check ;;
    runpod) mock_case runpod ;;
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
  ./scripts/run-benchmark.sh --provider "$PROVIDER" --image "ghcr.io/bie3yeik-lgtm/parakeet-rtf-benchmark@${RTF_IMAGE_DIGEST}"
  pass "live $PROVIDER provider verification completed; external resources were used"
}

case "$MODE" in
  static) static_checks ;;
  mock) static_checks; mock_checks ;;
  docker) static_checks; docker_checks ;;
  live) static_checks; live_checks ;;
  *) fail "unsupported mode: $MODE" ;;
esac
