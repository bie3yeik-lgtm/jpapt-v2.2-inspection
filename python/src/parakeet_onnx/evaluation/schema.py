"""Strict JSON Schema registry for execution and NeMo/ONNX evidence artifacts.

The registry validates structure. Semantic validation that is shared with a
producer/consumer lives next to the corresponding typed Python contract. The
Rust `asr-eval` binary remains the authority for runtime acceptance and ASR
quality acceptance.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from parakeet_onnx.config.paths import RepositoryPaths
from parakeet_onnx.nemo import parse_reference_document


class EvaluationSchemaError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        schema_name: str | None = None,
        instance_path: str | None = None,
        schema_path: str | None = None,
    ) -> None:
        self.schema_name = schema_name
        self.instance_path = instance_path
        self.schema_path = schema_path
        details = [message]
        if schema_name is not None:
            details.append(f"schema={schema_name}")
        if instance_path is not None:
            details.append(f"instance_path={instance_path}")
        if schema_path is not None:
            details.append(f"schema_path={schema_path}")
        super().__init__("; ".join(details))


def _json_path(parts: list[Any]) -> str:
    result = "$"
    for part in parts:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result


def _normalize_instance(instance: Any) -> Any:
    if hasattr(instance, "to_dict"):
        return instance.to_dict()
    if is_dataclass(instance):
        return asdict(instance)
    return instance


class EvaluationSchemaRegistry:
    RUN_CONTEXT = "run-context"
    SAMPLE_RESULT = "result"
    BENCHMARK = "benchmark"
    NEMO_ONNX_VALIDATION = "nemo-onnx-validation"
    NEMO_REFERENCE_QUALITY = "nemo-reference-quality"
    NEMO_ONNX_QUALITY = "nemo-onnx-quality"

    _FILES = {
        RUN_CONTEXT: "run-context.schema.json",
        SAMPLE_RESULT: "result.schema.json",
        BENCHMARK: "benchmark.schema.json",
        NEMO_ONNX_VALIDATION: "nemo-onnx-validation.schema.json",
        NEMO_REFERENCE_QUALITY: "nemo-reference-quality.schema.json",
        NEMO_ONNX_QUALITY: "nemo-onnx-quality.schema.json",
    }

    def __init__(self, repository_root: str | Path | None = None) -> None:
        self.paths = (
            RepositoryPaths.discover()
            if repository_root is None
            else RepositoryPaths(root=Path(repository_root).expanduser().resolve())
        )
        self.schema_root = self.paths.root / "evaluation" / "schemas"
        self._schemas: dict[str, dict[str, Any]] = {}
        self._validators: dict[str, Draft202012Validator] = {}

    def schema_path(self, schema_name: str) -> Path:
        try:
            filename = self._FILES[schema_name]
        except KeyError as exc:
            raise EvaluationSchemaError(
                f"Unknown evaluation schema: {schema_name}"
            ) from exc
        return self.schema_root / filename

    def load_schema(self, schema_name: str) -> dict[str, Any]:
        if schema_name in self._schemas:
            return self._schemas[schema_name]
        path = self.schema_path(schema_name)
        if not path.is_file():
            raise EvaluationSchemaError(
                f"Schema file does not exist: {path}", schema_name=schema_name
            )
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvaluationSchemaError(
                f"Invalid JSON Schema file: {exc}", schema_name=schema_name
            ) from exc
        if not isinstance(schema, dict):
            raise EvaluationSchemaError(
                "JSON Schema root must be an object", schema_name=schema_name
            )
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise EvaluationSchemaError(
                f"Invalid Draft 2020-12 schema: {exc.message}",
                schema_name=schema_name,
            ) from exc
        self._schemas[schema_name] = schema
        return schema

    def validator(self, schema_name: str) -> Draft202012Validator:
        if schema_name not in self._validators:
            self._validators[schema_name] = Draft202012Validator(
                self.load_schema(schema_name)
            )
        return self._validators[schema_name]

    def validate(self, schema_name: str, instance: Any) -> None:
        normalized = _normalize_instance(instance)
        errors = sorted(
            self.validator(schema_name).iter_errors(normalized),
            key=lambda error: (
                list(error.absolute_path),
                list(error.absolute_schema_path),
            ),
        )
        if errors:
            first = errors[0]
            message = first.message
            if len(errors) > 1:
                message += f" ({len(errors)} validation errors total; showing first)"
            raise EvaluationSchemaError(
                message,
                schema_name=schema_name,
                instance_path=_json_path(list(first.absolute_path)),
                schema_path=_json_path(list(first.absolute_schema_path)),
            )

        # The NeMo reference is produced by Python and consumed by Rust. Keep a
        # strict typed Python parser at the producer boundary in addition to JSON Schema.
        if schema_name == self.NEMO_REFERENCE_QUALITY:
            try:
                parse_reference_document(normalized)
            except (TypeError, ValueError) as exc:
                raise EvaluationSchemaError(
                    f"NeMo reference semantic contract failed: {exc}",
                    schema_name=schema_name,
                ) from exc

    def validate_run_context(self, instance: Any) -> None:
        self.validate(self.RUN_CONTEXT, instance)

    def validate_sample_result(self, instance: Any) -> None:
        self.validate(self.SAMPLE_RESULT, instance)

    def validate_benchmark(self, instance: Any) -> None:
        self.validate(self.BENCHMARK, instance)

    def validate_nemo_onnx_validation(self, instance: Any) -> None:
        self.validate(self.NEMO_ONNX_VALIDATION, instance)

    def validate_nemo_reference_quality(self, instance: Any) -> None:
        self.validate(self.NEMO_REFERENCE_QUALITY, instance)

    def validate_nemo_onnx_quality(self, instance: Any) -> None:
        self.validate(self.NEMO_ONNX_QUALITY, instance)


def _registry(repository_root: str | Path | None) -> EvaluationSchemaRegistry:
    return EvaluationSchemaRegistry(repository_root)


def validate_run_context(
    instance: Any, *, repository_root: str | Path | None = None
) -> None:
    _registry(repository_root).validate_run_context(instance)


def validate_sample_result(
    instance: Any, *, repository_root: str | Path | None = None
) -> None:
    _registry(repository_root).validate_sample_result(instance)


def validate_benchmark(
    instance: Any, *, repository_root: str | Path | None = None
) -> None:
    _registry(repository_root).validate_benchmark(instance)


def validate_nemo_onnx_validation(
    instance: Any, *, repository_root: str | Path | None = None
) -> None:
    _registry(repository_root).validate_nemo_onnx_validation(instance)


def validate_nemo_reference_quality(
    instance: Any, *, repository_root: str | Path | None = None
) -> None:
    _registry(repository_root).validate_nemo_reference_quality(instance)


def validate_nemo_onnx_quality(
    instance: Any, *, repository_root: str | Path | None = None
) -> None:
    _registry(repository_root).validate_nemo_onnx_quality(instance)
