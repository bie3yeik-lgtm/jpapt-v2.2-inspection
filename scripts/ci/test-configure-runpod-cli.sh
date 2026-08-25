#!/usr/bin/env bash
set -euo pipefail

test_dir="$(mktemp -d "${TMPDIR:-/tmp}/configure-runpod-cli-test.XXXXXX")"
mock_bin="$test_dir/bin"
mkdir -p "$mock_bin"

cat > "$mock_bin/runpodctl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  *doctor*)
    [[ -n "${RUNPOD_API_KEY:-}" ]] || { echo 'missing RUNPOD_API_KEY' >&2; exit 1; }
    if [[ "${MOCK_DOCTOR_MIXED_OUTPUT:-0}" == 1 ]]; then
      printf '%s\n' 'generating ssh key...' 'adding ssh key to runpod...' '{"healthy":true,"checks":[{"name":"api_key","status":"pass"}]}'
    else
      printf '%s\n' '{"healthy":true,"checks":[{"name":"api_key","status":"pass"}]}'
    fi
    ;;
  *)
    echo "unsupported mock runpodctl invocation: $*" >&2
    exit 2
    ;;
esac
MOCK
chmod +x "$mock_bin/runpodctl"

export PATH="$mock_bin:$PATH"

if bash scripts/ci/configure-runpod-cli.sh 2>/dev/null; then
  echo 'expected failure without RUNPOD_TOKEN' >&2
  exit 1
fi

grep -F 'export RUNPOD_API_KEY="$RUNPOD_TOKEN"' scripts/ci/configure-runpod-cli.sh >/dev/null
grep -F 'RUNPOD_API_KEY<<EOF' scripts/ci/configure-runpod-cli.sh >/dev/null

export RUNPOD_TOKEN=test-token
source scripts/ci/configure-runpod-cli.sh --doctor >/dev/null
[[ "${RUNPOD_API_KEY:-}" == test-token ]] || {
  echo "source did not persist RUNPOD_API_KEY: ${RUNPOD_API_KEY:-<unset>}" >&2
  exit 1
}

github_env="$test_dir/github_env"
touch "$github_env"
export GITHUB_ENV="$github_env"
unset RUNPOD_API_KEY
source scripts/ci/configure-runpod-cli.sh >/dev/null
grep -F 'RUNPOD_API_KEY<<EOF' "$github_env" >/dev/null
grep -Fx 'test-token' "$github_env" >/dev/null

export MOCK_DOCTOR_MIXED_OUTPUT=1
source scripts/ci/configure-runpod-cli.sh --doctor 2>/dev/null | jq -e '.healthy == true' >/dev/null

echo 'configure-runpod-cli tests passed'
