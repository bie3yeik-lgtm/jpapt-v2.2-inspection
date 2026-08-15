#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from parakeet_onnx.hf.revisions import (
    RevisionError,
    load_revision_bundle,
)


DEFAULT_ROOT = Path(".ci/hf/config/revisions")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the three pinned Hugging Face revision documents and "
            "print their combined identity."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=(
            "Directory containing reference.json, evaluation-schema.json, "
            "and datasets-lock.json."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the normalized revision bundle as JSON.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.expanduser().resolve()

    try:
        bundle = load_revision_bundle(root)
    except (RevisionError, FileNotFoundError, OSError, ValueError) as exc:
        print(
            f"ERROR: revision validation failed: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(
            json.dumps(
                bundle.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("Revision documents are valid.")
        print(f"root: {root}")
        print(f"bundle_sha256: {bundle.sha256}")
        print(
            "model: "
            f"{bundle.reference.model_id}"
            f"@{bundle.reference.model_revision}"
        )
        print(
            "evaluation_schema: "
            f"{bundle.evaluation_schema.schema_id}"
            f"@{bundle.evaluation_schema.schema_revision}"
        )
        print(f"datasets: {len(bundle.datasets.datasets)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
