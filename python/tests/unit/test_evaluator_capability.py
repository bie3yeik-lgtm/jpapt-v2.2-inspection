from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ci" / "validate-evaluator-capability.py"


def _run(evaluator: str, decoder: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repository-root",
            str(ROOT),
            "--evaluator",
            evaluator,
            "--decoder",
            decoder,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_python_ctc_is_supported() -> None:
    result = _run("python-onnx", "ctc")
    assert result.returncode == 0, result.stderr


def test_rust_ctc_is_supported() -> None:
    result = _run("rust-onnx", "ctc")
    assert result.returncode == 0, result.stderr


def test_python_whisper_is_rejected_by_capability_contract() -> None:
    result = _run("python-onnx", "whisper_autoregressive")
    assert result.returncode == 1
    assert "evaluator capability mismatch" in result.stderr


def test_rust_tdt_is_rejected_by_capability_contract() -> None:
    result = _run("rust-onnx", "tdt")
    assert result.returncode == 1
    assert "evaluator capability mismatch" in result.stderr
