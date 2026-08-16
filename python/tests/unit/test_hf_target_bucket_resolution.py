from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ci" / "resolve-hf-target.py"


def _mapping() -> str:
    return json.dumps(
        {
            "kotoba-whisper-v1.0": {
                "HF_BUCKET": "gawohok7/tf-v1-onnx-dev-bucket",
                "HF_MODEL_REPO": "gawohok7/tf-v1-onnx-dev",
            },
            "parakeet-tdt_ctc-0.6b-ja": {
                "HF_BUCKET": "gawohok7/jpapt-v2.2-dev-bucket",
                "HF_MODEL_REPO": "gawohok7/jpapt-v2.2-dev",
            },
        }
    )


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repository-root",
            str(ROOT),
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_bucket_resolves_kotoba_target() -> None:
    result = _run(
        "--bucket",
        "gawohok7/tf-v1-onnx-dev-bucket",
        "--targets-json",
        _mapping(),
    )

    assert result.returncode == 0, result.stderr
    assert "HF_TARGET_ID=kotoba-whisper-v1.0" in result.stdout
    assert "HF_MODEL_REPO=gawohok7/tf-v1-onnx-dev" in result.stdout
    assert "EXPECTED_UPSTREAM_REPO_ID=kotoba-tech/kotoba-whisper-v1.0" in result.stdout
    assert "EXPECTED_TOKENIZER_REPO_ID=kotoba-tech/kotoba-whisper-v1.0" in result.stdout


def test_unknown_bucket_is_rejected() -> None:
    result = _run(
        "--bucket",
        "gawohok7/not-configured-bucket",
        "--targets-json",
        _mapping(),
    )

    assert result.returncode == 1
    assert "is not present in HF target mapping" in result.stderr
    assert "gawohok7/tf-v1-onnx-dev-bucket" in result.stderr


def test_duplicate_bucket_is_rejected() -> None:
    mapping = json.dumps(
        {
            "kotoba-whisper-v1.0": {
                "HF_BUCKET": "gawohok7/shared-bucket",
                "HF_MODEL_REPO": "gawohok7/tf-v1-onnx-dev",
            },
            "parakeet-tdt_ctc-0.6b-ja": {
                "HF_BUCKET": "gawohok7/shared-bucket",
                "HF_MODEL_REPO": "gawohok7/jpapt-v2.2-dev",
            },
        }
    )

    result = _run(
        "--bucket",
        "gawohok7/shared-bucket",
        "--targets-json",
        mapping,
    )

    assert result.returncode == 1
    assert "is assigned to both" in result.stderr
