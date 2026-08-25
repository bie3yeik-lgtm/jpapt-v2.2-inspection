#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

grep -F 'RTF_RUNPOD_BILLING_ATTEMPTS' scripts/ci/enrich_runpod_job_metrics.py >/dev/null
grep -F 'RTF_RUNPOD_BILLING_RETRY_SECONDS' scripts/ci/enrich_runpod_job_metrics.py >/dev/null
grep -F 'RUNPOD_API_KEY' scripts/ci/enrich_runpod_job_metrics.py >/dev/null
grep -F 'RunPod billing history empty for Pod' scripts/ci/enrich_runpod_job_metrics.py >/dev/null

mise exec -- uv run python -m py_compile scripts/ci/enrich_runpod_job_metrics.py
mise exec -- uv run python -m pytest -q python/tests/unit/test_enrich_runpod_job_metrics.py

echo 'PASS test-enrich-runpod-job-metrics.sh'
