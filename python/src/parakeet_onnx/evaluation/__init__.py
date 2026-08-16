"""Evaluation contracts and Python-first orchestration."""

from .aggregate import AggregateResult, aggregate_sample_results
from .capsule_reader import (
    ExperimentCapsule,
    ExperimentCapsuleError,
    read_experiment_capsule,
    validate_experiment_capsule,
)
from .factory import EvaluatorBuildRequest, create_python_evaluator
from .metrics import (
    CorpusErrorAccumulator,
    character_error_rate,
    edit_distance,
    normalize_text,
    word_error_rate,
)
from .models import *
from .parquet import EXPERIMENT_CAPSULE_SCHEMA_VERSION, ExperimentCapsuleWriter
from .pipeline import PythonAsrEvaluator, PythonCtcEvaluator
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
    "EXPERIMENT_CAPSULE_SCHEMA_VERSION",
    "EvaluationRunInputs",
    "EvaluationSchemaError",
    "EvaluationSchemaRegistry",
    "EvaluatorBuildRequest",
    "ExperimentCapsule",
    "ExperimentCapsuleError",
    "ExperimentCapsuleWriter",
    "PythonAsrEvaluator",
    "PythonCtcEvaluator",
    "SampleResultWriter",
    "aggregate_sample_results",
    "character_error_rate",
    "create_python_evaluator",
    "edit_distance",
    "normalize_text",
    "read_experiment_capsule",
    "run_evaluation",
    "validate_benchmark",
    "validate_experiment_capsule",
    "validate_run_context",
    "validate_sample_result",
    "word_error_rate",
    "write_benchmark",
]
