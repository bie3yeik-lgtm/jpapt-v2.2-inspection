#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

runner_root="docker/rtf-benchmark/benchmark-runner"
profiler_module="$runner_root/benchmark_runner/pytorch_profiler.py"

python -m py_compile "$profiler_module" "$runner_root/benchmark_runner/cli.py"
grep -F 'RTF_PYTORCH_PROFILER_OUTPUT_DIR=/output/profiler' docker/rtf-benchmark/Dockerfile >/dev/null
grep -F 'benchmark_runner.pytorch_profiler' docker/rtf-benchmark/Dockerfile >/dev/null
grep -F 'RTF_PYTORCH_PROFILER_TABLE_BEGIN' "$profiler_module" >/dev/null
grep -F 'pytorch_profiler.pytorch_profiler_enabled()' "$runner_root/benchmark_runner/cli.py" >/dev/null

PYTHONPATH="$runner_root" python -m unittest discover -s "$runner_root/tests" -p 'test_pytorch_profiler.py' -v

PYTHONPATH="$runner_root" python - <<'PY'
from benchmark_runner.pytorch_profiler import (
    PROFILER_TABLE_BEGIN,
    PROFILER_TABLE_END,
    emit_profiler_summary,
)

import io
from contextlib import redirect_stdout

buffer = io.StringIO()
with redirect_stdout(buffer):
    emit_profiler_summary("aten::linear    1.000\n")
output = buffer.getvalue()
assert PROFILER_TABLE_BEGIN in output
assert "aten::linear" in output
assert PROFILER_TABLE_END in output
print("PyTorch Profiler GitHub Actions log markers: PASS")
PY

if command -v torch >/dev/null 2>&1 || python -c 'import torch' >/dev/null 2>&1; then
  PYTHONPATH="$runner_root" python -m benchmark_runner.pytorch_profiler --smoke-test
  echo "PyTorch Profiler torch smoke test: PASS"
else
  echo "PyTorch Profiler torch smoke test: SKIP (torch not installed on host)"
fi

echo "PASS test-pytorch-profiler-contract.sh"
