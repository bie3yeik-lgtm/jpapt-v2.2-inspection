"""
Evaluation result models, JSON Schema validation, and output writers.

This package defines the language-neutral evaluation output contract used by:

- Python evaluation runtime
- future Rust evaluation runtime
- GitHub Actions
- Hugging Face Bucket runs/
- Hugging Face Bucket benchmarks/

Primary output files:

    run-context.json
    samples.jsonl
    metrics.json
"""

from .models import (
    AcceptanceSummary,
    AsrOutput,
    BenchmarkResult,
    CandidateIdentity,
    ComponentTimingSummary,
    ErrorRecord,
    ErrorSummary,
    EvaluationIdentity,
    ExecutionIdentity,
    MemoryMetrics,
    MemorySummary,
    NumericParity,
    NumericSummary,
    ParityResult,
    ParitySummary,
    PerformanceSummary,
    ProviderResult,
    ProviderSummary,
    QualityMetrics,
    QualitySummary,
    RuntimeIdentity,
    SampleIdentity,
    SampleResult,
    SampleSummary,
    TensorComparison,
    TensorSummary,
    TimingDistribution,
    TimingMetrics,
)
from .schema import (
    EvaluationSchemaError,
    EvaluationSchemaRegistry,
    validate_benchmark,
    validate_run_context,
    validate_sample_result,
)
from .writer import (
    BenchmarkWriter,
    SampleResultWriter,
    write_benchmark,
)

__all__ = [
    "AcceptanceSummary",
    "AsrOutput",
    "BenchmarkResult",
    "BenchmarkWriter",
    "CandidateIdentity",
    "ComponentTimingSummary",
    "ErrorRecord",
    "ErrorSummary",
    "EvaluationIdentity",
    "EvaluationSchemaError",
    "EvaluationSchemaRegistry",
    "ExecutionIdentity",
    "MemoryMetrics",
    "MemorySummary",
    "NumericParity",
    "NumericSummary",
    "ParityResult",
    "ParitySummary",
    "PerformanceSummary",
    "ProviderResult",
    "ProviderSummary",
    "QualityMetrics",
    "QualitySummary",
    "RuntimeIdentity",
    "SampleIdentity",
    "SampleResult",
    "SampleResultWriter",
    "SampleSummary",
    "TensorComparison",
    "TensorSummary",
    "TimingDistribution",
    "TimingMetrics",
    "validate_benchmark",
    "validate_run_context",
    "validate_sample_result",
    "write_benchmark",
]
