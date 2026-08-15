"""Evaluation contracts and Python-first orchestration."""

from .aggregate import AggregateResult, aggregate_sample_results
from .metrics import (
    CorpusErrorAccumulator,
    character_error_rate,
    edit_distance,
    normalize_text,
    word_error_rate,
)
from .models import *
from .pipeline import PythonCtcEvaluator
from .runner import EvaluationRunInputs, run_evaluation
from .schema import (
    EvaluationSchemaError,
    EvaluationSchemaRegistry,
    validate_benchmark,
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
    "PythonCtcEvaluator",
    "SampleResultWriter",
    "aggregate_sample_results",
    "character_error_rate",
    "edit_distance",
    "normalize_text",
    "run_evaluation",
    "validate_benchmark",
    "validate_run_context",
    "validate_sample_result",
    "word_error_rate",
    "write_benchmark",
]
