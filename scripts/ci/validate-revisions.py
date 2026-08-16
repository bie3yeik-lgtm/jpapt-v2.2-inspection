#!/usr/bin/env python3
"""Deprecated compatibility shim for Rust revision validation.

Operational callers should invoke:

    cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
        validate-revisions ...

This file intentionally contains no revision parsing or validation policy.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
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
        "validate-revisions",
        *sys.argv[1:],
    ]
    print(
        "WARNING: scripts/ci/validate-revisions.py is deprecated; invoking Rust asr-contracts.",
        file=sys.stderr,
    )
    os.execvp(command[0], command)
    raise AssertionError("os.execvp unexpectedly returned")


if __name__ == "__main__":
    raise SystemExit(main())
