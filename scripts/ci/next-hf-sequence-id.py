#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys


ID_SUFFIX = re.compile(r"-(\d{6})$")
PREFIX = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")


def next_sequence_id(prefix: str, paths: list[str]) -> str:
    if not PREFIX.fullmatch(prefix):
        raise ValueError(
            "prefix must contain only lowercase ASCII letters, digits, '.', '_', "
            "or '-', and must start/end with an alphanumeric character"
        )

    maximum = 0
    for raw in paths:
        value = raw.strip()
        if not value:
            continue

        # `hf buckets list <bucket>/<collection> -R -q` returns paths relative
        # to the listed collection. Only the first path component identifies
        # the allocated directory; nested files must not influence allocation.
        directory = value.split("/", 1)[0].rstrip("/")
        match = ID_SUFFIX.search(directory)
        if match is None:
            continue
        maximum = max(maximum, int(match.group(1)))

    next_value = maximum + 1
    if next_value > 999_999:
        raise ValueError("six-digit HF sequence space is exhausted")

    return f"{prefix}-{next_value:06d}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate prefix-NNNNNN from the largest six-digit suffix present "
            "in an HF Bucket collection listing."
        )
    )
    parser.add_argument("--prefix", required=True)
    parser.add_argument(
        "--listing",
        default="-",
        help="Listing file produced by `hf buckets list ... -R -q`, or '-' for stdin.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.listing == "-":
            paths = sys.stdin.read().splitlines()
        else:
            with open(args.listing, "r", encoding="utf-8") as file:
                paths = file.read().splitlines()
        print(next_sequence_id(args.prefix, paths))
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
