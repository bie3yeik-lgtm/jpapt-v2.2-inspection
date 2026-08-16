#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate that an evaluator supports the resolved decoder contract."
    )
    parser.add_argument("--evaluator", required=True)
    parser.add_argument("--decoder", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = (
        args.repository_root.expanduser().resolve()
        / "config"
        / "evaluators"
        / f"{args.evaluator}.toml"
    )
    if not path.is_file():
        print(f"ERROR: evaluator capability file not found: {path}", file=sys.stderr)
        return 1

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        evaluator = raw["evaluator"]
        capabilities = raw["capabilities"]
        evaluator_id = evaluator["id"]
        supported = capabilities["supported_decoders"]
    except (KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        print(f"ERROR: invalid evaluator capability file {path}: {exc}", file=sys.stderr)
        return 1

    if evaluator_id != args.evaluator:
        print(
            f"ERROR: evaluator id mismatch: requested={args.evaluator!r}, configured={evaluator_id!r}",
            file=sys.stderr,
        )
        return 1
    if not isinstance(supported, list) or not all(
        isinstance(value, str) and value for value in supported
    ):
        print("ERROR: capabilities.supported_decoders must be a non-empty string list", file=sys.stderr)
        return 1
    if args.decoder not in supported:
        print(
            "ERROR: evaluator capability mismatch: "
            f"evaluator={args.evaluator!r}, decoder={args.decoder!r}, "
            f"supported={supported!r}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Evaluator capability OK: evaluator={args.evaluator}, decoder={args.decoder}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
