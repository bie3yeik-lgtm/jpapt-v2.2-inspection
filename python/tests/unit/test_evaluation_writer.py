from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jsonschema")


def test_evaluation_package_imports() -> None:
    import parakeet_onnx.evaluation as evaluation

    assert evaluation is not None
