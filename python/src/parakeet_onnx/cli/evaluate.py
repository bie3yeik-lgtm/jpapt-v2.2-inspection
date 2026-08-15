from __future__ import annotations

import argparse
from pathlib import Path

from parakeet_onnx.runtime import OrtSessionConfig, create_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakeet-onnx-evaluate",
        description="Validate that an ONNX candidate can be loaded by ONNX Runtime.",
    )
    parser.add_argument("--provider", default="cpu")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--datasets-lock", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    session = create_session(
        OrtSessionConfig(
            model_path=args.model,
            provider_id=args.provider,
        )
    )
    print("providers:", session.get_providers())
    print("inputs:", [item.name for item in session.get_inputs()])
    print("outputs:", [item.name for item in session.get_outputs()])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
