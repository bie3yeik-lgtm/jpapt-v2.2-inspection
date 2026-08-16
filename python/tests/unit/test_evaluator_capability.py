from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import onnx
from onnx import TensorProto, helper


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
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _save(path: Path, inputs: list[object], outputs: list[object]) -> None:
    onnx.save(helper.make_model(helper.make_graph([], path.stem, inputs, outputs)), path)


def _write_whisper_candidate(root: Path) -> None:
    tokenizer = root / "tokenizer"
    tokenizer.mkdir()
    (tokenizer / "generation_config.json").write_text(
        json.dumps(
            {
                "decoder_start_token_id": 1,
                "forced_decoder_ids": [[1, 2]],
                "eos_token_id": 3,
                "max_new_tokens": 64,
                "suppress_tokens": [],
            }
        ),
        encoding="utf-8",
    )
    (tokenizer / "tokenizer_config.json").write_text("{}\n", encoding="utf-8")

    _save(
        root / "encoder.onnx",
        [helper.make_tensor_value_info("input_features", TensorProto.FLOAT, [1, 80, "frames"])],
        [helper.make_tensor_value_info("last_hidden_state", TensorProto.FLOAT, [1, "frames", 64])],
    )
    _save(
        root / "decoder.onnx",
        [
            helper.make_tensor_value_info("input_ids", TensorProto.INT64, [1, "tokens"]),
            helper.make_tensor_value_info("encoder_hidden_states", TensorProto.FLOAT, [1, "frames", 64]),
        ],
        [
            helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, "tokens", 32]),
            helper.make_tensor_value_info("present.key", TensorProto.FLOAT, [1, 1, "tokens", 64]),
        ],
    )
    _save(
        root / "decoder_with_past.onnx",
        [
            helper.make_tensor_value_info("input_ids", TensorProto.INT64, [1, 1]),
            helper.make_tensor_value_info("encoder_hidden_states", TensorProto.FLOAT, [1, "frames", 64]),
            helper.make_tensor_value_info("past.key", TensorProto.FLOAT, [1, 1, "tokens", 64]),
        ],
        [
            helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 1, 32]),
            helper.make_tensor_value_info("present.key", TensorProto.FLOAT, [1, 1, "tokens", 64]),
        ],
    )
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "profile_set": "whisper-autoregressive-v1",
                "variants": {
                    "whisper": {
                        "artifacts": {
                            "encoder": "encoder.onnx",
                            "decoder": "decoder.onnx",
                            "decoder_with_past": "decoder_with_past.onnx",
                        },
                        "tokenizer": "tokenizer",
                    }
                },
            }
        ),
        encoding="utf-8",
    )


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


def test_candidate_requirements_are_derived_from_catalog(tmp_path: Path) -> None:
    _write_whisper_candidate(tmp_path)
    result = _run(
        "python-onnx",
        "whisper_autoregressive",
        provider="cpu",
        candidate_dir=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "whisper-autoregressive-v1" in result.stdout
    assert "'kv_cache': True" in result.stdout
    assert "'multi_graph': True" in result.stdout
    assert "'transformers_processor': True" in result.stdout
    assert "'external_frontend': True" in result.stdout
    assert "'timestamps': False" in result.stdout


def test_candidate_decoder_mismatch_is_rejected_after_derivation(tmp_path: Path) -> None:
    _write_whisper_candidate(tmp_path)
    result = _run(
        "python-onnx",
        "ctc",
        provider="cpu",
        candidate_dir=tmp_path,
    )
    assert result.returncode == 1
    assert "candidate decoder mismatch" in result.stderr
    assert "whisper_autoregressive" in result.stderr
