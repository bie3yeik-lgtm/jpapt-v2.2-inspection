from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
import onnxruntime as ort


_LEVELS = (
    ort.GraphOptimizationLevel.ORT_DISABLE_ALL,
    ort.GraphOptimizationLevel.ORT_ENABLE_BASIC,
    ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED,
    ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
)


def _build_canary(path: Path) -> None:
    weights = np.asarray(
        [
            [0.5, -0.25, 0.75, 0.125],
            [-0.5, 0.5, 0.25, -0.75],
            [1.0, 0.125, -0.5, 0.25],
            [0.25, 0.75, -0.125, 0.5],
        ],
        dtype=np.float32,
    )
    bias = np.asarray([0.25, -0.5, 0.125, 0.75], dtype=np.float32)
    graph = helper.make_graph(
        [
            helper.make_node("MatMul", ["x", "weights"], ["projected"]),
            helper.make_node("Add", ["projected", "bias"], ["biased"]),
            helper.make_node("Relu", ["biased"], ["output"]),
        ],
        "ort-optimizer-canary",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [2, 4])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [2, 4])],
        initializer=[
            numpy_helper.from_array(weights, name="weights"),
            numpy_helper.from_array(bias, name="bias"),
        ],
    )
    model = helper.make_model(
        graph,
        producer_name="jpapt-ort-canary",
        opset_imports=[helper.make_operatorsetid("", 17)],
    )
    model.ir_version = min(model.ir_version, 9)
    onnx.checker.check_model(model)
    onnx.save(model, path)


def _run(path: Path, level: ort.GraphOptimizationLevel) -> np.ndarray:
    options = ort.SessionOptions()
    options.graph_optimization_level = level
    session = ort.InferenceSession(
        str(path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    source = np.asarray(
        [[0.25, -1.0, 0.5, 2.0], [-0.5, 1.5, -2.0, 0.125]],
        dtype=np.float32,
    )
    values = session.run(["output"], {"x": source})
    assert len(values) == 1
    result = np.asarray(values[0])
    assert result.shape == (2, 4)
    assert np.all(np.isfinite(result))
    return result


def test_ort_optimizer_levels_preserve_canary_semantics(tmp_path: Path) -> None:
    assert ort.__version__ == "1.28.0"
    model = tmp_path / "optimizer-canary.onnx"
    _build_canary(model)

    baseline = _run(model, _LEVELS[0])
    for level in _LEVELS[1:]:
        candidate = _run(model, level)
        np.testing.assert_allclose(candidate, baseline, rtol=1.0e-6, atol=1.0e-7)
