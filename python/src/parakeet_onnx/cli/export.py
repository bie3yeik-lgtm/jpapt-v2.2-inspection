from __future__ import annotations

import argparse
from pathlib import Path

from parakeet_onnx.export import export_ctc_candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakeet-onnx-export",
        description="Export a pinned NeMo ASR model to an ONNX candidate.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--decoder", choices=("ctc", "tdt"), default="ctc")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.decoder == "tdt":
        raise SystemExit("TDT export is intentionally not implemented yet.")
    export_ctc_candidate(
        output_dir=args.output,
        candidate_id=args.candidate_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
