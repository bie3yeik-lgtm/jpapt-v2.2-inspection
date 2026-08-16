from __future__ import annotations

import argparse
from pathlib import Path

from parakeet_onnx.export import (
    export_ctc_candidate,
    export_tdt_candidate,
    export_whisper_candidate,
)


UNALLOCATED_CANDIDATE_ID = "unallocated"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakeet-onnx-export",
        description=(
            "Finalize framework-exported ONNX graphs into a canonical local candidate. "
            "The durable HF candidate ID is allocated by hf-push-candidate.sh."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--candidate-id",
        default=UNALLOCATED_CANDIDATE_ID,
        help=(
            "Optional provisional local ID. Durable prefix-NNNNNN allocation happens "
            "when publishing to the HF Bucket."
        ),
    )
    parser.add_argument(
        "--decoder",
        choices=("ctc", "tdt", "whisper_autoregressive"),
        default="ctc",
    )
    parser.add_argument(
        "--runtime-contract",
        type=Path,
        default=None,
        help="Defaults to <output>/runtime-contract.json.",
    )
    parser.add_argument(
        "--tokenizer-path",
        default=None,
        help=(
            "Candidate-relative tokenizer/processor path. Defaults to vocabulary.json "
            "for CTC/TDT and tokenizer/ for Whisper."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.decoder == "ctc":
        export_ctc_candidate(
            output_dir=args.output,
            candidate_id=args.candidate_id,
            runtime_contract_path=args.runtime_contract,
            tokenizer_path=args.tokenizer_path or "vocabulary.json",
        )
    elif args.decoder == "tdt":
        export_tdt_candidate(
            output_dir=args.output,
            candidate_id=args.candidate_id,
            runtime_contract_path=args.runtime_contract,
            tokenizer_path=args.tokenizer_path or "vocabulary.json",
        )
    else:
        export_whisper_candidate(
            output_dir=args.output,
            candidate_id=args.candidate_id,
            runtime_contract_path=args.runtime_contract,
            processor_path=args.tokenizer_path or "tokenizer",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
