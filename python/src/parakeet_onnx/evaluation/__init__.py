"""Evaluation structures.

Python keeps diagnostic/orchestration helpers, but release acceptance and
NeMo-reference vs ONNX ASR quality authority live in the Rust `asr-eval` CLI.
"""

from .aggregate import AggregateResult, aggregate_sample_results
from .factory import EvaluatorBuildRequest, create_python_evaluator
from .metrics import (
    CorpusErrorAccumulator,
    character_error_rate,
    edit_distance,
    normalize_text,
    word_error_rate,
)
from .models import *
from .pipeline import PythonAsrEvaluator, PythonCtcEvaluator
from .runner import EvaluationRunInputs, run_evaluation
from .schema import (
    EvaluationSchemaError,
    EvaluationSchemaRegistry,
    validate_benchmark,
    validate_nemo_onnx_quality,
    validate_nemo_onnx_validation,
    validate_nemo_reference_quality,
    validate_run_context,
    validate_sample_result,
)
from .writer import BenchmarkWriter, SampleResultWriter, write_benchmark

__all__ = [
    "AggregateResult",
    "BenchmarkWriter",
    "CorpusErrorAccumulator",
    "EvaluationRunInputs",
    "EvaluationSchemaError",
    "EvaluationSchemaRegistry",
    "EvaluatorBuildRequest",
    "PythonAsrEvaluator",
    "PythonCtcEvaluator",
    "SampleResultWriter",
    "aggregate_sample_results",
    "character_error_rate",
    "create_python_evaluator",
    "edit_distance",
    "normalize_text",
    "run_evaluation",
    "validate_benchmark",
    "validate_nemo_onnx_quality",
    "validate_nemo_onnx_validation",
    "validate_nemo_reference_quality",
    "validate_run_context",
    "validate_sample_result",
    "word_error_rate",
    "write_benchmark",
]
