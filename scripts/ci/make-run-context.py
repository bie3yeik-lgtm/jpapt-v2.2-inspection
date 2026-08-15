#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from parakeet_onnx.config import (
    ConfigError,
    resolve_config,
)
from parakeet_onnx.evaluation import (
    EvaluationSchemaError,
    validate_run_context,
)
from parakeet_onnx.hf.revisions import (
    RevisionError,
    load_revision_bundle,
)
from parakeet_onnx.run_context import (
    build_run_context,
)


DEFAULT_REVISIONS = Path(".ci/hf/config/revisions")


def _metadata(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}

    path = Path(value)
    if path.is_file():
        raw = path.read_text(encoding="utf-8")
    else:
        raw = value

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(
            "--metadata-json must resolve to a JSON object."
        )

    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build and validate a canonical run-context.json from project "
            "configuration, pinned revisions, and a candidate artifact."
        )
    )

    parser.add_argument(
        "--model",
        default="parakeet-tdt_ctc-0.6b-ja",
    )
    parser.add_argument(
        "--provider",
        required=True,
        choices=("cpu", "cuda", "directml", "coreml"),
    )
    parser.add_argument(
        "--evaluation",
        required=True,
        choices=("smoke", "parity", "full"),
    )
    parser.add_argument(
        "--environment",
        choices=("linux", "windows", "macos"),
        default=None,
    )

    parser.add_argument(
        "--candidate",
        type=Path,
        required=True,
        help="Actual ONNX artifact used for evaluation.",
    )
    parser.add_argument(
        "--candidate-id",
        default=None,
    )
    parser.add_argument(
        "--artifact-role",
        default="primary",
    )

    parser.add_argument(
        "--revisions",
        type=Path,
        default=DEFAULT_REVISIONS,
        help="Local directory containing the three HF revision documents.",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Optional explicit run ID. Normally omitted so the canonical "
            "builder creates one."
        ),
    )
    parser.add_argument(
        "--metadata-json",
        default=None,
        help=(
            "Optional JSON object or path to a JSON file containing extra "
            "non-authoritative run metadata."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination run-context.json.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    repository_root = (
        args.repository_root.expanduser().resolve()
        if args.repository_root is not None
        else None
    )

    try:
        config = resolve_config(
            model=args.model,
            provider=args.provider,
            evaluation=args.evaluation,
            environment=args.environment,
            repository_root=repository_root,
        )

        revisions = load_revision_bundle(
            args.revisions.expanduser().resolve()
        )

        context = build_run_context(
            config=config,
            revisions=revisions,
            candidate_path=args.candidate,
            candidate_id=args.candidate_id,
            artifact_role=args.artifact_role,
            metadata=_metadata(args.metadata_json),
            run_id=args.run_id,
        )

        validate_run_context(
            context,
            repository_root=config.repository_root,
        )

        output = args.output.expanduser()
        context.write_json(output)

    except (
        ConfigError,
        RevisionError,
        EvaluationSchemaError,
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"ERROR: failed to create run context: {exc}",
            file=sys.stderr,
        )
        return 1

    print("Run context created.")
    print(f"run_id: {context.run_id}")
    print(f"output: {output.resolve()}")
    print(f"artifact_sha256: {context.artifact.sha256}")
    print(
        "revision_bundle_sha256: "
        f"{revisions.sha256}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
