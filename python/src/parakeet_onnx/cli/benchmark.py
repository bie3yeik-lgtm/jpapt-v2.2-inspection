from __future__ import annotations

import argparse
from pathlib import Path

from parakeet_onnx.runtime import OrtSessionConfig, create_session, input_metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakeet-onnx-benchmark",
        description="Run a minimal ONNX Runtime session benchmark.",
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--provider", default="cpu")
    parser.add_argument("--iterations", type=int, default=5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    session = create_session(OrtSessionConfig(model_path=args.model, provider_id=args.provider))
    print("inputs:", input_metadata(session))
    print("providers:", session.get_providers())
    print(
        "Session creation/metadata benchmark only; model-specific synthetic "
        "input generation is intentionally not guessed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
