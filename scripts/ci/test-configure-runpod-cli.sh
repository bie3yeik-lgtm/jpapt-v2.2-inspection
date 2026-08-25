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
    printf '%s\n' '{"healthy":true,"checks":[{"name":"api_key","status":"pass"}]}'
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

export RUNPOD_TOKEN=test-token
bash scripts/ci/configure-runpod-cli.sh --doctor >/dev/null

echo 'configure-runpod-cli tests passed'
