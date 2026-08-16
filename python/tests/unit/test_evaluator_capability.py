from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ci" / "validate-evaluator-capability.py"


def _run(
    evaluator: str,
    decoder: str,
    *,
    provider: str | None = None,
    candidate_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--repository-root",
        str(ROOT),
        "--evaluator",
        evaluator,
        "--decoder",
        decoder,
    ]
    if provider is not None:
        command += ["--provider", provider]
    if candidate_dir is not None:
        command += ["--candidate-dir", str(candidate_dir)]
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def _artifact(path: Path) -> dict[str, object]:
    path.write_bytes(path.name.encode("utf-8"))
    return {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _write_whisper_candidate(root: Path, *, timestamps: bool = False) -> None:
    (root / "tokenizer").mkdir()
    metadata = {
        "schema_version": 2,
        "candidate_id": "whisper-000002",
        "decoder": "whisper_autoregressive",
        "artifact_contract": "whisper-autoregressive-v1",
        "artifacts": {
            "encoder": _artifact(root / "encoder.onnx"),
            "decoder": _artifact(root / "decoder.onnx"),
            "decoder_with_past": _artifact(root / "decoder_with_past.onnx"),
        },
        "runtime_contract": {
            "decoder": "whisper_autoregressive",
            "input_kind": "features",
            "io": {
                "encoder": {"input": "features", "output": "hidden"},
                "decoder": {
                    "input_ids": "input_ids",
                    "encoder_hidden_states": "hidden",
                    "logits_output": "logits",
                    "past_outputs": ["present.key"],
                },
                "decoder_with_past": {
                    "input_ids": "input_ids",
                    "encoder_hidden_states": "hidden",
                    "logits_output": "logits",
                    "past_inputs": ["past.key"],
                    "past_outputs": ["present.key"],
                },
            },
            "decoder_config": {
                "prompt_token_ids": [1, 2],
                "eos_token_id": 3,
                "timestamps": timestamps,
            },
        },
        "tokenizer": {"kind": "transformers_processor", "path": "tokenizer"},
        "features": {
            "kv_cache": True,
            "multi_graph": True,
            "transformers_processor": True,
            "external_frontend": True,
            "timestamps": timestamps,
        },
    }
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_python_ctc_is_supported() -> None:
    result = _run("python-onnx", "ctc", provider="cpu")
    assert result.returncode == 0, result.stderr


def test_python_tdt_is_supported() -> None:
    result = _run("python-onnx", "tdt", provider="cpu")
    assert result.returncode == 0, result.stderr


def test_python_whisper_is_supported() -> None:
    result = _run("python-onnx", "whisper_autoregressive", provider="coreml")
    assert result.returncode == 0, result.stderr


def test_rust_ctc_is_supported() -> None:
    result = _run("rust-onnx", "ctc", provider="cpu")
    assert result.returncode == 0, result.stderr


def test_rust_tdt_is_rejected_by_capability_contract() -> None:
    result = _run("rust-onnx", "tdt")
    assert result.returncode == 1
    assert "evaluator capability mismatch" in result.stderr


def test_candidate_required_feature_is_checked(tmp_path: Path) -> None:
    _write_whisper_candidate(tmp_path, timestamps=True)
    result = _run(
        "python-onnx",
        "whisper_autoregressive",
        provider="cpu",
        candidate_dir=tmp_path,
    )
    assert result.returncode == 1
    assert "unsupported evaluator feature" in result.stderr
    assert "timestamps" in result.stderr


def test_candidate_contract_and_features_pass_when_supported(tmp_path: Path) -> None:
    _write_whisper_candidate(tmp_path)
    result = _run(
        "python-onnx",
        "whisper_autoregressive",
        provider="cpu",
        candidate_dir=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "whisper-autoregressive-v1" in result.stdout
