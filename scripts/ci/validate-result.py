#!/usr/bin/env python3
"""Deprecated compatibility shim for the Rust result validator.

New callers should invoke:

    cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
        validate-run <result-directory>

This file intentionally contains no evaluation-contract logic.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper around the Rust evaluation result validator."
    )
    parser.add_argument("result_dir", type=Path)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=None,
        help="Deprecated and ignored; Rust resolves embedded source-controlled schemas.",
    )
    parser.add_argument(
        "--allow-empty-samples",
        action="store_true",
        help="Deprecated. Empty result sets are not accepted by the canonical Rust validator.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.allow_empty_samples:
        print(
            "ERROR: --allow-empty-samples is not supported by the canonical Rust validator.",
            file=sys.stderr,
        )
        return 2

    result_dir = args.result_dir.expanduser().resolve()
    command = [
        "cargo",
        "run",
        "--quiet",
        "--locked",
        "-p",
        "asr-contracts",
        "--bin",
        "asr-contracts",
        "--",
        "validate-run",
        str(result_dir),
    ]

    print(
        "WARNING: scripts/ci/validate-result.py is deprecated; invoking Rust asr-contracts.",
        file=sys.stderr,
    )
    os.execvp(command[0], command)
    raise AssertionError("os.execvp unexpectedly returned")


if __name__ == "__main__":
    raise SystemExit(main())
