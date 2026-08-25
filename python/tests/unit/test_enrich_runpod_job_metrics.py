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


def test_billing_retry_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RTF_RUNPOD_BILLING_ATTEMPTS", raising=False)
    monkeypatch.delenv("RTF_RUNPOD_BILLING_RETRY_SECONDS", raising=False)
    assert enrich.billing_retry_config() == (40, 15.0)


def test_billing_retry_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RTF_RUNPOD_BILLING_ATTEMPTS", "12")
    monkeypatch.setenv("RTF_RUNPOD_BILLING_RETRY_SECONDS", "5")
    assert enrich.billing_retry_config() == (12, 5.0)


def test_resolve_runpod_token_prefers_canonical_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNPOD_TOKEN", "canonical")
    monkeypatch.setenv("RUNPOD_API_KEY", "api-key")
    monkeypatch.setenv("RUNPOD_API", "legacy")
    assert enrich.resolve_runpod_token() == "canonical"


def test_fetch_billing_history_retries_until_record_appears() -> None:
    calls = {"count": 0}

    def fake_request(_url: str, _token: str) -> list[dict[str, object]]:
        calls["count"] += 1
        if calls["count"] < 3:
            return []
        return [
            {
                "podId": "pod-1",
                "amount": 0.25,
                "timeBilledMs": 120_000,
                "gpuTypeId": "NVIDIA RTX 2000 Ada Generation",
            }
        ]

    sleeps: list[float] = []
    records = enrich.fetch_billing_history(
        "pod-1",
        "token",
        attempts=5,
        retry_seconds=2.0,
        request_json=fake_request,
        sleep=sleeps.append,
        log=lambda _message: None,
    )

    assert calls["count"] == 3
    assert sleeps == [2.0, 2.0]
    assert records[0]["podId"] == "pod-1"


def test_fetch_billing_history_raises_after_exhausted_attempts() -> None:
    with pytest.raises(RuntimeError, match="no record for Pod pod-missing"):
        enrich.fetch_billing_history(
            "pod-missing",
            "token",
            attempts=2,
            retry_seconds=0.0,
            request_json=lambda _url, _token: [],
            sleep=lambda _seconds: None,
            log=lambda _message: None,
        )


def test_build_billing_metadata() -> None:
    metadata = enrich.build_billing_metadata(
        "pod-1",
        [
            {
                "podId": "pod-1",
                "amount": 0.10,
                "timeBilledMs": 60_000,
                "gpuTypeId": "NVIDIA RTX 2000 Ada Generation",
            },
            {
                "podId": "pod-1",
                "amount": 0.05,
                "timeBilledMs": 30_000,
                "gpuTypeId": "NVIDIA RTX 2000 Ada Generation",
            },
        ],
    )
    assert metadata["job_id"] == "pod-1"
    assert metadata["job_cost_usd"] == pytest.approx(0.15)
    assert metadata["billing_duration_sec"] == pytest.approx(90.0)
    assert metadata["billed_seconds"] == 90
    assert metadata["cost_basis"] == "runpod_billing_history"
