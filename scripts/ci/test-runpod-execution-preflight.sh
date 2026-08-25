#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

bash -n scripts/ci/run-runpod-execution-preflight.sh
grep -F 'probe_billing_api' scripts/ci/enrich_runpod_job_metrics.py >/dev/null
grep -F 'run-runpod-execution-preflight.sh --phase runner' scripts/run-benchmark.sh >/dev/null
grep -F -- '--phase remote' scripts/run-benchmark.sh >/dev/null

mise exec -- uv run python -m pytest -q python/tests/unit/test_runpod_execution_preflight.py

export RTF_RUNPOD_PREFLIGHT_SKIP_BILLING_PROBE=1
export HF_TOKEN=local-test-token
export RUNPOD_TOKEN=local-test-token
runner_output="$(bash scripts/ci/run-runpod-execution-preflight.sh --phase runner 2>&1)"
grep -F 'phase=runner check=summary status=pass' <<<"$runner_output" >/dev/null

mock_root="$(mktemp -d)"
mkdir -p "$mock_root/bin"
cat > "$mock_root/bin/ssh" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
case " $* " in
  *' nvidia-smi && test -e /dev/nvidia0 '*)
    printf '%s\n' 'CUDA Version: 13.0' ;;
  *' nvidia-smi --query-gpu=name --format=csv,noheader '*)
    printf '%s\n' 'NVIDIA RTX A5000' ;;
  *' test -x /opt/rtf-benchmark/entrypoint.sh '*|*'test -x /opt/rtf-benchmark/entrypoint.sh'*) : ;;
  *' test -d /output && test -w /output '*|*'test -d /output && test -w /output'*) : ;;
  *' df -h /output '*)
    printf '%s\n' 'tmpfs 100G 1G 99G 1% /output' ;;
  *) exit 1 ;;
esac
MOCK
chmod +x "$mock_root/bin/ssh"
PATH="$mock_root/bin:$PATH" \
  bash scripts/ci/run-runpod-execution-preflight.sh \
    --phase remote \
    --pod-id pod-test \
    --gpu-id "NVIDIA RTX A5000" \
    --min-cuda-version 13.0 \
    --ssh-command "ssh -o BatchMode=yes mock@runpod" \
    --pod-state-json '{"id":"pod-test","gpu":{"id":"NVIDIA RTX A5000"}}' \
    2>&1 | grep -F 'phase=remote check=summary status=pass' >/dev/null
rm -rf "$mock_root"

echo 'PASS test-runpod-execution-preflight.sh'
