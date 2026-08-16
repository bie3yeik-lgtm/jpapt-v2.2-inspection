from __future__ import annotations

import argparse
from pathlib import Path

from parakeet_onnx.export import (
    export_ctc_candidate,
    export_tdt_candidate,
    export_whisper_candidate,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakeet-onnx-export",
        description=(
            "Finalize framework-exported ONNX graphs into a minimal local candidate. "
            "Artifact identity and runtime bindings are derived automatically."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--decoder",
        choices=("ctc", "tdt", "whisper_autoregressive"),
        default="ctc",
    )
    parser.add_argument(
        "--tokenizer-path",
        default=None,
        help=(
            "Optional candidate-relative tokenizer/processor path. Omit it when the "
            "candidate uses a conventional tokenizer/ or vocabulary.json layout."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.decoder == "ctc":
        export_ctc_candidate(
            output_dir=args.output,
            tokenizer_path=args.tokenizer_path,
        )
    elif args.decoder == "tdt":
        export_tdt_candidate(
            output_dir=args.output,
            tokenizer_path=args.tokenizer_path,
        )
    else:
        export_whisper_candidate(
            output_dir=args.output,
            processor_path=args.tokenizer_path,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
