from __future__ import annotations

from pathlib import Path


def test_expected_project_directories_exist() -> None:
    root = Path(__file__).resolve().parents[3]

    expected = [
        "config",
        "evaluation",
        "python/src/parakeet_onnx",
        "scripts",
        "docs",
        "docker",
        "tools",
    ]

    missing = [item for item in expected if not (root / item).exists()]

    assert missing == []
