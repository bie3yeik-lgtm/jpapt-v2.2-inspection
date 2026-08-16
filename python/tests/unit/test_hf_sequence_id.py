from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ci" / "next-hf-sequence-id.py"
SPEC = importlib.util.spec_from_file_location("next_hf_sequence_id", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_empty_collection_starts_at_one() -> None:
    assert MODULE.next_sequence_id("export", []) == "export-000001"


def test_all_prefixes_share_one_collection_sequence() -> None:
    paths = [
        "whisper-export-000001/README.md",
        "whisper-export-000001/encoder.onnx",
        "ctc-export-000004/README.md",
        "cpu-full-eval-000003/README.md",
    ]
    assert MODULE.next_sequence_id("whisper-export", paths) == "whisper-export-000005"


def test_example_000001_makes_first_real_id_000002() -> None:
    paths = ["structure-example-000001/README.md"]
    assert MODULE.next_sequence_id("cpu-full-eval", paths) == "cpu-full-eval-000002"


def test_nested_numeric_filenames_do_not_allocate_ids() -> None:
    paths = [
        "candidate-000002/logs/output-999999.txt",
        "candidate-000002/artifacts/model-888888.onnx",
    ]
    assert MODULE.next_sequence_id("candidate", paths) == "candidate-000003"


def test_invalid_prefix_is_rejected() -> None:
    with pytest.raises(ValueError, match="prefix"):
        MODULE.next_sequence_id("CPU Full Eval", [])
