from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakeet-onnx-compare",
        description="Compare two JSON benchmark/result documents.",
    )
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    if reference == candidate:
        print("documents are identical")
        return 0
    print("documents differ")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
