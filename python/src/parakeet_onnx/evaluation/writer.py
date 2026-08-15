"""
Evaluation result writers.

Output contract:

    results/<provider-or-result-name>/
    ├── run-context.json
    ├── samples.jsonl
    └── metrics.json

samples.jsonl:
    One result.schema.json-compatible JSON object per line.

metrics.json:
    One benchmark.schema.json-compatible JSON document.

Each object is validated before it becomes a durable result.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Iterable

from .models import (
    BenchmarkResult,
    SampleResult,
)
from .schema import EvaluationSchemaRegistry


def _atomic_write_text(
    destination: Path,
    text: str,
) -> None:
    """
    Atomically replace a text file.

    Prevents partially-written metrics.json if the process is interrupted.
    """

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )

    temporary = Path(temporary_name)

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())

        os.replace(
            temporary,
            destination,
        )

    finally:
        if temporary.exists():
            temporary.unlink()


class SampleResultWriter:
    """
    Incremental samples.jsonl writer.

    Validation is performed before each line is appended.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        schema_registry: EvaluationSchemaRegistry | None = None,
        validate: bool = True,
    ) -> None:
        self.path = Path(path)
        self.validate = validate

        self.schema_registry = (
            schema_registry
            if schema_registry is not None
            else EvaluationSchemaRegistry()
        )

        self._file = None
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def __enter__(self) -> "SampleResultWriter":
        self.open()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()

    def open(self) -> None:
        if self._file is not None:
            return

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._file = self.path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        )

    def close(self) -> None:
        if self._file is None:
            return

        self._file.flush()
        os.fsync(self._file.fileno())
        self._file.close()

        self._file = None

    def write(
        self,
        result: SampleResult,
    ) -> None:
        if self._file is None:
            raise RuntimeError(
                "SampleResultWriter is not open."
            )

        value = result.to_dict()

        if self.validate:
            self.schema_registry.validate_sample_result(
                value
            )

        line = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        self._file.write(line)
        self._file.write("\n")

        self._count += 1

    def write_many(
        self,
        results: Iterable[SampleResult],
    ) -> int:
        initial = self._count

        for result in results:
            self.write(result)

        return self._count - initial


class BenchmarkWriter:
    """
    Write metrics.json with schema validation and atomic replacement.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        schema_registry: EvaluationSchemaRegistry | None = None,
        validate: bool = True,
    ) -> None:
        self.path = Path(path)
        self.validate = validate

        self.schema_registry = (
            schema_registry
            if schema_registry is not None
            else EvaluationSchemaRegistry()
        )

    def write(
        self,
        benchmark: BenchmarkResult,
    ) -> None:
        value = benchmark.to_dict()

        if self.validate:
            self.schema_registry.validate_benchmark(
                value
            )

        payload = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

        _atomic_write_text(
            self.path,
            payload + "\n",
        )


def write_benchmark(
    benchmark: BenchmarkResult,
    path: str | Path,
    *,
    schema_registry: EvaluationSchemaRegistry | None = None,
    validate: bool = True,
) -> None:
    """
    Convenience API for writing one metrics.json.
    """

    BenchmarkWriter(
        path,
        schema_registry=schema_registry,
        validate=validate,
    ).write(benchmark)
