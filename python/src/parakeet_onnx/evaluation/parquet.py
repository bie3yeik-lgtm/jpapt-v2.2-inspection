"""ExperimentCapsuleV1 Parquet output."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Iterator, Mapping

from parakeet_onnx.contracts import RunContext

from .capsule_artifacts import CapsuleArtifact, iter_artifact_parts
from .capsule_diagnostics import CapsuleDiagnostic
from .models import BenchmarkResult, SampleResult


EXPERIMENT_CAPSULE_SCHEMA_VERSION = "experiment-capsule/v1"
DEFAULT_CAPSULE_ROW_BATCH_SIZE = 512

_CAPSULE_COLUMNS = (
    "schema_version",
    "run_id",
    "record_kind",
    "ordinal",
    "name",
    "category",
    "metadata_json",
    "sample_id",
    "dataset_id",
    "dataset_repo_id",
    "dataset_revision",
    "subset",
    "split",
    "audio_sha256",
    "audio_duration_sec",
    "sample_rate_hz",
    "reference_text",
    "hypothesis_text",
    "normalized_text",
    "cer",
    "wer",
    "provider_id",
    "decoder",
    "load_ms",
    "session_creation_ms",
    "audio_decode_ms",
    "resample_ms",
    "frontend_ms",
    "encoder_ms",
    "inference_ms",
    "decoder_ms",
    "postprocess_ms",
    "total_ms",
    "rtf",
    "peak_ram_mb",
    "peak_device_memory_mb",
    "status",
    "error_code",
    "error_stage",
    "error_message",
    "metric_name",
    "metric_value",
    "metric_unit",
    "artifact_id",
    "artifact_name",
    "mime_type",
    "artifact_sha256",
    "artifact_size_raw",
    "artifact_part_index",
    "artifact_part_count",
    "artifact_offset",
    "artifact_part_sha256",
    "payload",
)


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _empty_row(*, run_id: str, record_kind: str, ordinal: int) -> dict[str, Any]:
    row = dict.fromkeys(_CAPSULE_COLUMNS)
    row.update(
        {
            "schema_version": EXPERIMENT_CAPSULE_SCHEMA_VERSION,
            "run_id": run_id,
            "record_kind": record_kind,
            "ordinal": ordinal,
        }
    )
    return row


def _metric_unit(name: str) -> str | None:
    if name.endswith("_ms"):
        return "ms"
    if name.endswith("_sec"):
        return "s"
    if name.endswith("_mb"):
        return "MB"
    if name.endswith("_bytes"):
        return "bytes"
    return None


def _iter_numeric_metrics(
    value: Mapping[str, Any],
    *,
    prefix: str = "",
) -> Iterable[tuple[str, float, str | None]]:
    for key in sorted(value):
        item = value[key]
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, Mapping):
            yield from _iter_numeric_metrics(item, prefix=name)
        elif isinstance(item, bool) or item is None:
            continue
        elif isinstance(item, (int, float)):
            yield name, float(item), _metric_unit(key)


def _sample_row(
    value: Mapping[str, Any],
    *,
    ordinal: int,
    expected_run_id: str,
) -> dict[str, Any]:
    run_id = value.get("run_id")
    if run_id != expected_run_id:
        raise ValueError(
            "sample result run_id does not match capsule run_id: "
            f"sample={run_id!r}, capsule={expected_run_id!r}"
        )

    sample = value["sample"]
    execution = value["execution"]
    output = value["output"]
    quality = value["quality"]
    timing = value["timing"]
    memory = value["memory"]
    errors = value.get("errors", [])
    first_error = errors[0] if errors else {}

    row = _empty_row(
        run_id=expected_run_id,
        record_kind="sample",
        ordinal=ordinal,
    )
    row.update(
        {
            "sample_id": sample["id"],
            "dataset_id": sample["dataset_id"],
            "dataset_repo_id": sample["dataset_repo_id"],
            "dataset_revision": sample["dataset_revision"],
            "subset": sample.get("subset"),
            "split": sample.get("split"),
            "audio_sha256": sample.get("audio_sha256"),
            "audio_duration_sec": sample["audio_duration_sec"],
            "sample_rate_hz": sample["sample_rate_hz"],
            "reference_text": sample["reference_text"],
            "hypothesis_text": output["text"],
            "normalized_text": output["normalized_text"],
            "cer": quality.get("cer"),
            "wer": quality.get("wer"),
            "provider_id": execution["provider_id"],
            "decoder": execution["decoder"],
            "load_ms": timing.get("load_ms"),
            "session_creation_ms": timing.get("session_creation_ms"),
            "audio_decode_ms": timing.get("audio_decode_ms"),
            "resample_ms": timing.get("resample_ms"),
            "frontend_ms": timing.get("frontend_ms"),
            "encoder_ms": timing.get("encoder_ms"),
            "inference_ms": timing.get("inference_ms"),
            "decoder_ms": timing.get("decoder_ms"),
            "postprocess_ms": timing.get("postprocess_ms"),
            "total_ms": timing.get("total_ms"),
            "rtf": timing.get("rtf"),
            "peak_ram_mb": memory.get("peak_ram_mb"),
            "peak_device_memory_mb": memory.get("peak_device_memory_mb"),
            "status": value["status"],
            "error_code": first_error.get("code"),
            "error_stage": first_error.get("stage"),
            "error_message": first_error.get("message"),
            "metadata_json": _json(
                {
                    "sample_index": sample.get("index"),
                    "execution": execution,
                    "tokens": output.get("tokens", []),
                    "token_count": output.get("token_count"),
                    "parity": value.get("parity"),
                    "provider": value.get("provider"),
                    "errors": errors,
                }
            ),
        }
    )
    return row


def _diagnostic_row(
    diagnostic: CapsuleDiagnostic,
    *,
    run_id: str,
    ordinal: int,
) -> dict[str, Any]:
    row = _empty_row(
        run_id=run_id,
        record_kind="diagnostic",
        ordinal=ordinal,
    )
    row.update(
        {
            "name": diagnostic.name,
            "category": diagnostic.category,
            "status": diagnostic.status,
            "error_code": diagnostic.code,
            "error_stage": diagnostic.stage,
            "error_message": diagnostic.message,
            "metadata_json": _json(dict(diagnostic.metadata)),
        }
    )
    return row


def iter_experiment_capsule_rows(
    *,
    run_context: Mapping[str, Any],
    samples: Iterable[Mapping[str, Any]],
    benchmark: Mapping[str, Any],
    artifacts: Iterable[CapsuleArtifact] = (),
    diagnostics: Iterable[CapsuleDiagnostic] = (),
) -> Iterator[dict[str, Any]]:
    """Yield deterministic capsule rows without materializing the complete run."""

    run_id = run_context.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_context must contain a non-empty run_id")
    if benchmark.get("run_id") != run_id:
        raise ValueError("benchmark run_id does not match run_context run_id")

    ordinal = 0
    manifest = _empty_row(run_id=run_id, record_kind="manifest", ordinal=ordinal)
    manifest.update(
        {
            "name": "run",
            "category": "evaluation",
            "metadata_json": _json(
                {
                    "run_context": run_context,
                    "benchmark": benchmark,
                }
            ),
        }
    )
    yield manifest
    ordinal += 1

    for sample in samples:
        yield _sample_row(
            sample,
            ordinal=ordinal,
            expected_run_id=run_id,
        )
        ordinal += 1

    metric_sections = (
        "samples",
        "quality",
        "performance",
        "memory",
        "parity",
        "provider",
        "errors",
    )
    for section in metric_sections:
        section_value = benchmark.get(section)
        if not isinstance(section_value, Mapping):
            continue
        for metric_name, metric_value, metric_unit in _iter_numeric_metrics(
            section_value,
            prefix=section,
        ):
            row = _empty_row(
                run_id=run_id,
                record_kind="metric",
                ordinal=ordinal,
            )
            row.update(
                {
                    "metric_name": metric_name,
                    "metric_value": metric_value,
                    "metric_unit": metric_unit,
                }
            )
            yield row
            ordinal += 1

    artifact_ids: set[str] = set()
    for artifact in artifacts:
        parts = list(iter_artifact_parts(artifact))
        if not parts:
            continue
        artifact_id = str(parts[0]["artifact_id"])
        if artifact_id in artifact_ids:
            raise ValueError(f"duplicate artifact_id: {artifact_id}")
        artifact_ids.add(artifact_id)
        for part in parts:
            row = _empty_row(
                run_id=run_id,
                record_kind="artifact",
                ordinal=ordinal,
            )
            row.update(part)
            yield row
            ordinal += 1

    for diagnostic in diagnostics:
        yield _diagnostic_row(
            diagnostic,
            run_id=run_id,
            ordinal=ordinal,
        )
        ordinal += 1


def build_experiment_capsule_rows(
    *,
    run_context: Mapping[str, Any],
    samples: Iterable[Mapping[str, Any]],
    benchmark: Mapping[str, Any],
    artifacts: Iterable[CapsuleArtifact] = (),
    diagnostics: Iterable[CapsuleDiagnostic] = (),
) -> list[dict[str, Any]]:
    """Compatibility helper that materializes all deterministic capsule rows."""

    return list(
        iter_experiment_capsule_rows(
            run_context=run_context,
            samples=samples,
            benchmark=benchmark,
            artifacts=artifacts,
            diagnostics=diagnostics,
        )
    )


def iter_experiment_capsule_row_batches(
    *,
    run_context: Mapping[str, Any],
    samples: Iterable[Mapping[str, Any]],
    benchmark: Mapping[str, Any],
    artifacts: Iterable[CapsuleArtifact] = (),
    diagnostics: Iterable[CapsuleDiagnostic] = (),
    batch_size: int = DEFAULT_CAPSULE_ROW_BATCH_SIZE,
) -> Iterator[tuple[dict[str, Any], ...]]:
    """Yield bounded row batches for a future streaming Arrow/Parquet writer."""

    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("batch_size must be a positive integer")

    batch: list[dict[str, Any]] = []
    for row in iter_experiment_capsule_rows(
        run_context=run_context,
        samples=samples,
        benchmark=benchmark,
        artifacts=artifacts,
        diagnostics=diagnostics,
    ):
        batch.append(row)
        if len(batch) >= batch_size:
            yield tuple(batch)
            batch.clear()

    if batch:
        yield tuple(batch)


def _features() -> Any:
    try:
        from datasets import Features, Value
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Parquet capsule output requires the project's 'datasets' optional dependency."
        ) from exc

    nullable_strings = {
        "name",
        "category",
        "metadata_json",
        "sample_id",
        "dataset_id",
        "dataset_repo_id",
        "dataset_revision",
        "subset",
        "split",
        "audio_sha256",
        "reference_text",
        "hypothesis_text",
        "normalized_text",
        "provider_id",
        "decoder",
        "status",
        "error_code",
        "error_stage",
        "error_message",
        "metric_name",
        "metric_unit",
        "artifact_id",
        "artifact_name",
        "mime_type",
        "artifact_sha256",
        "artifact_part_sha256",
    }
    float_columns = {
        "audio_duration_sec",
        "cer",
        "wer",
        "load_ms",
        "session_creation_ms",
        "audio_decode_ms",
        "resample_ms",
        "frontend_ms",
        "encoder_ms",
        "inference_ms",
        "decoder_ms",
        "postprocess_ms",
        "total_ms",
        "rtf",
        "peak_ram_mb",
        "peak_device_memory_mb",
        "metric_value",
    }
    int32_columns = {
        "sample_rate_hz",
        "artifact_part_index",
        "artifact_part_count",
    }
    int64_columns = {
        "ordinal",
        "artifact_size_raw",
        "artifact_offset",
    }

    mapping: dict[str, Any] = {
        "schema_version": Value("string"),
        "run_id": Value("string"),
        "record_kind": Value("string"),
        "payload": Value("binary"),
    }
    mapping.update({name: Value("string") for name in nullable_strings})
    mapping.update({name: Value("float64") for name in float_columns})
    mapping.update({name: Value("int32") for name in int32_columns})
    mapping.update({name: Value("int64") for name in int64_columns})
    return Features({name: mapping[name] for name in _CAPSULE_COLUMNS})


def _atomic_write_parquet(destination: Path, rows: list[dict[str, Any]]) -> None:
    try:
        from datasets import Dataset
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Parquet capsule output requires the project's 'datasets' optional dependency."
        ) from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(fd)
    temporary = Path(temporary_name)

    try:
        dataset = Dataset.from_list(rows, features=_features())
        dataset.to_parquet(str(temporary))
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


class ExperimentCapsuleWriter:
    """Write one immutable-in-concept ``run.parquet`` capsule."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write(
        self,
        *,
        run_context: RunContext,
        samples: Iterable[SampleResult],
        benchmark: BenchmarkResult,
        artifacts: Iterable[CapsuleArtifact] = (),
        diagnostics: Iterable[CapsuleDiagnostic] = (),
    ) -> None:
        sample_values = [sample.to_dict() for sample in samples]
        rows = build_experiment_capsule_rows(
            run_context=run_context.to_dict(),
            samples=sample_values,
            benchmark=benchmark.to_dict(),
            artifacts=artifacts,
            diagnostics=diagnostics,
        )
        _atomic_write_parquet(self.path, rows)
