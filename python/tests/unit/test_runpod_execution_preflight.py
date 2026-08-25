from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "ci" / "enrich_runpod_job_metrics.py"
SPEC = importlib.util.spec_from_file_location("enrich_runpod_job_metrics", MODULE_PATH)
assert SPEC and SPEC.loader
enrich = importlib.util.module_from_spec(SPEC)
sys.modules["enrich_runpod_job_metrics"] = enrich
SPEC.loader.exec_module(enrich)


def test_probe_billing_api_accepts_list_response() -> None:
    enrich.probe_billing_api(
        "token",
        request_json=lambda _url, _token: [],
    )


def test_probe_billing_api_rejects_non_list_response() -> None:
    with pytest.raises(ValueError, match="billing probe response is not a list"):
        enrich.probe_billing_api(
            "token",
            request_json=lambda _url, _token: {"error": "bad"},
        )
