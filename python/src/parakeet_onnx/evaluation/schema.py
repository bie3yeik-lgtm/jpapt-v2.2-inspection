"""Structural and semantic validation for evaluation JSON artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from parakeet_onnx.config.paths import RepositoryPaths
from parakeet_onnx.contract_io import parse_run_context
from parakeet_onnx.contracts import ContractError, RunContext


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

    _FILES = {
        RUN_CONTEXT: "run-context.schema.json",
        SAMPLE_RESULT: "result.schema.json",
        BENCHMARK: "benchmark.schema.json",
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
        cached = self._schemas.get(schema_name)
        if cached is not None:
            return cached
        path = self.schema_path(schema_name)
        if not path.is_file():
            raise EvaluationSchemaError(
                f"Schema file does not exist: {path}", schema_name=schema_name
            )
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EvaluationSchemaError(
                f"Invalid JSON Schema file: {exc}", schema_name=schema_name
            ) from exc
        if not isinstance(schema, dict):
            raise EvaluationSchemaError(
                "JSON Schema root must be an object.", schema_name=schema_name
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
        cached = self._validators.get(schema_name)
        if cached is not None:
            return cached
        validator = Draft202012Validator(self.load_schema(schema_name))
        self._validators[schema_name] = validator
        return validator

    def validate(self, schema_name: str, instance: Any) -> None:
        normalized = _normalize_instance(instance)
        errors = sorted(
            self.validator(schema_name).iter_errors(normalized),
            key=lambda error: (
                list(error.absolute_path),
                list(error.absolute_schema_path),
            ),
        )
        if not errors:
            return
        first = errors[0]
        message = first.message
        if len(errors) > 1:
            message += f" ({len(errors)} validation errors total; showing the first)"
        raise EvaluationSchemaError(
            message,
            schema_name=schema_name,
            instance_path=_json_path(list(first.absolute_path)),
            schema_path=_json_path(list(first.absolute_schema_path)),
        )

    def validate_run_context(self, instance: Any) -> None:
        self.validate(self.RUN_CONTEXT, instance)
        if isinstance(instance, RunContext):
            instance.validate()
            return
        try:
            parse_run_context(_normalize_instance(instance))
        except ContractError as exc:
            raise EvaluationSchemaError(
                f"run-context semantic contract violation: {exc}",
                schema_name=self.RUN_CONTEXT,
            ) from exc

    def validate_sample_result(self, instance: Any) -> None:
        self.validate(self.SAMPLE_RESULT, instance)

    def validate_benchmark(self, instance: Any) -> None:
        self.validate(self.BENCHMARK, instance)


def validate_run_context(
    instance: Any, *, repository_root: str | Path | None = None
) -> None:
    EvaluationSchemaRegistry(repository_root).validate_run_context(instance)


def validate_sample_result(
    instance: Any, *, repository_root: str | Path | None = None
) -> None:
    EvaluationSchemaRegistry(repository_root).validate_sample_result(instance)


def validate_benchmark(
    instance: Any, *, repository_root: str | Path | None = None
) -> None:
    EvaluationSchemaRegistry(repository_root).validate_benchmark(instance)
