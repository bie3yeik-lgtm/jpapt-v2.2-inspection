#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from parakeet_onnx.config.allocation_catalog import load_repository_allocation_catalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    sub = parser.add_subparsers(dest="command", required=True)

    prefix = sub.add_parser("prefix")
    prefix.add_argument("key")

    candidate = sub.add_parser("candidate-prefix-key")
    candidate.add_argument("profile_set_id")

    fingerprint = sub.add_parser("fingerprint")
    fingerprint.add_argument("field", choices=["catalog_id", "sha256"])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    catalog = load_repository_allocation_catalog(args.repository_root)
    if args.command == "prefix":
        print(catalog.prefix(args.key))
        return 0
    if args.command == "candidate-prefix-key":
        print(catalog.candidate_prefix_key(args.profile_set_id))
        return 0
    print(getattr(catalog, args.field))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
