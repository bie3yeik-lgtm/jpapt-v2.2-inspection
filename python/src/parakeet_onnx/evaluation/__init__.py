"""Evaluation contracts and Python-first orchestration."""

from .aggregate import AggregateResult, aggregate_sample_results
from .capsule_analytics import (
    CapsuleMetricComparison,
    CapsuleRunSummary,
    RtfServiceRecord,
    compare_capsule_metric,
    rank_rtf_services,
    summarize_experiment_capsule,
    summarize_experiment_capsules,
)
from .capsule_artifacts import (
    MAX_EMBEDDED_ARTIFACT_BYTES,
    CapsuleArtifact,
    CapsuleArtifactError,
    EmbeddedCapsuleArtifact,
    ExternalCapsuleArtifact,
)
from .capsule_diagnostics import CapsuleDiagnostic, CapsuleDiagnosticError
from .capsule_reader import (
    ExperimentCapsule,
    ExperimentCapsuleError,
    read_experiment_capsule,
    validate_experiment_capsule,
)
from .capsule_streaming_writer import (
    CAPSULE_PARQUET_COMPRESSION,
    CAPSULE_PARQUET_COMPRESSION_LEVEL,
    CAPSULE_PARQUET_WRITER_VERSION,
    StreamingExperimentCapsuleWriter,
    capsule_arrow_schema,
    write_capsule_row_batches,
)
from .factory import EvaluatorBuildRequest, create_python_evaluator
from .metrics import (
    CorpusErrorAccumulator,
    character_error_rate,
    edit_distance,
    normalize_text,
    word_error_rate,
)
from .parquet import (
    DEFAULT_CAPSULE_ROW_BATCH_SIZE,
    EXPERIMENT_CAPSULE_SCHEMA_VERSION,
    ExperimentCapsuleWriter,
    iter_experiment_capsule_row_batches,
    iter_experiment_capsule_rows,
)
from .pipeline import PythonAsrEvaluator, PythonCtcEvaluator
from .rtf import RtfMetrics, calculate_rtf
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
    "CAPSULE_PARQUET_COMPRESSION",
    "CAPSULE_PARQUET_COMPRESSION_LEVEL",
    "CAPSULE_PARQUET_WRITER_VERSION",
    "CapsuleArtifact",
    "CapsuleArtifactError",
    "CapsuleDiagnostic",
    "CapsuleDiagnosticError",
    "CapsuleMetricComparison",
    "CapsuleRunSummary",
    "CorpusErrorAccumulator",
    "RtfServiceRecord",
    "DEFAULT_CAPSULE_ROW_BATCH_SIZE",
    "EmbeddedCapsuleArtifact",
    "EXPERIMENT_CAPSULE_SCHEMA_VERSION",
    "EvaluationRunInputs",
    "EvaluationSchemaError",
    "EvaluationSchemaRegistry",
    "EvaluatorBuildRequest",
    "ExperimentCapsule",
    "ExperimentCapsuleError",
    "ExperimentCapsuleWriter",
    "ExternalCapsuleArtifact",
    "MAX_EMBEDDED_ARTIFACT_BYTES",
    "PythonAsrEvaluator",
    "PythonCtcEvaluator",
    "SampleResultWriter",
    "StreamingExperimentCapsuleWriter",
    "aggregate_sample_results",
    "capsule_arrow_schema",
    "character_error_rate",
    "compare_capsule_metric",
    "create_python_evaluator",
    "edit_distance",
    "iter_experiment_capsule_row_batches",
    "iter_experiment_capsule_rows",
    "normalize_text",
    "read_experiment_capsule",
    "rank_rtf_services",
    "RtfMetrics",
    "run_evaluation",
    "calculate_rtf",
    "summarize_experiment_capsule",
    "summarize_experiment_capsules",
    "validate_benchmark",
    "validate_experiment_capsule",
    "validate_run_context",
    "validate_sample_result",
    "word_error_rate",
    "write_benchmark",
    "write_capsule_row_batches",
]
