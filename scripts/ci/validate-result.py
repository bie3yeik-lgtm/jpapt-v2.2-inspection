#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from parakeet_onnx.evaluation import (
    EvaluationSchemaError,
    validate_benchmark,
    validate_run_context,
    validate_sample_result,
)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {path}: {exc}"
        ) from exc


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue

            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSONL in {path}:{line_number}: {exc}"
                ) from exc

            yield line_number, value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one evaluation result directory against the Git-tracked "
            "JSON Schemas."
        )
    )
    parser.add_argument(
        "result_dir",
        type=Path,
        help=(
            "Directory containing run-context.json, samples.jsonl, and "
            "metrics.json."
        ),
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=None,
        help=(
            "Optional repository root. Normally auto-detected by "
            "parakeet_onnx."
        ),
    )
    parser.add_argument(
        "--allow-empty-samples",
        action="store_true",
        help=(
            "Allow samples.jsonl to contain zero records. Intended only for "
            "early pipeline diagnostics."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result_dir = args.result_dir.expanduser().resolve()

    run_context_path = result_dir / "run-context.json"
    samples_path = result_dir / "samples.jsonl"
    metrics_path = result_dir / "metrics.json"

    required = (
        run_context_path,
        samples_path,
        metrics_path,
    )

    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print(
            "ERROR: required evaluation output files are missing:",
            file=sys.stderr,
        )
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        return 1

    repository_root = (
        args.repository_root.expanduser().resolve()
        if args.repository_root is not None
        else None
    )

    try:
        run_context = _load_json(run_context_path)
        validate_run_context(
            run_context,
            repository_root=repository_root,
        )

        sample_count = 0
        for line_number, sample in _iter_jsonl(samples_path):
            try:
                validate_sample_result(
                    sample,
                    repository_root=repository_root,
                )
            except EvaluationSchemaError as exc:
                raise EvaluationSchemaError(
                    f"{samples_path}:{line_number}: {exc}"
                ) from exc
            sample_count += 1

        if sample_count == 0 and not args.allow_empty_samples:
            raise ValueError(
                f"{samples_path} contains no sample records."
            )

        benchmark = _load_json(metrics_path)
        validate_benchmark(
            benchmark,
            repository_root=repository_root,
        )

    except (
        EvaluationSchemaError,
        FileNotFoundError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"ERROR: result validation failed: {exc}",
            file=sys.stderr,
        )
        return 1

    print("Evaluation result is valid.")
    print(f"result_dir: {result_dir}")
    print(f"samples: {sample_count}")

    run_id = (
        run_context.get("run_id")
        if isinstance(run_context, dict)
        else None
    )
    if run_id:
        print(f"run_id: {run_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
