#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

grep -F 'RTF_RUNPOD_BILLING_ATTEMPTS' scripts/ci/enrich_runpod_job_metrics.py >/dev/null
grep -F 'RTF_RUNPOD_BILLING_RETRY_SECONDS' scripts/ci/enrich_runpod_job_metrics.py >/dev/null
grep -F 'RUNPOD_API_KEY' scripts/ci/enrich_runpod_job_metrics.py >/dev/null
grep -F 'RTF_RUNPOD_BILLING_MAX_WAIT_SECONDS' scripts/ci/enrich_runpod_job_metrics.py >/dev/null
grep -F 'RTF_COST_MODE' scripts/ci/enrich_runpod_job_metrics.py >/dev/null
grep -F 'FULL_MATRIX_BILLING_RETRY_MARGIN_SECONDS' scripts/ci/enrich_runpod_job_metrics.py >/dev/null
grep -F 'RTF_COST_MODE: ${{ inputs.cost_mode }}' .github/workflows/rtf-benchmark-run.yml >/dev/null

mise exec -- uv run python -m py_compile scripts/ci/enrich_runpod_job_metrics.py
mise exec -- uv run python -m pytest -q python/tests/unit/test_enrich_runpod_job_metrics.py

echo 'PASS test-enrich-runpod-job-metrics.sh'
