from __future__ import annotations

import argparse
import json
from pathlib import Path

from parakeet_onnx.nemo import MODEL_REPO, build_reference_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakeet-nemo-reference",
        description=(
            "Generate strict NeMo CTC transcript evidence for the canonical "
            "nvidia/parakeet-tdt_ctc-0.6b-ja quality comparison path."
        ),
    )
    parser.add_argument("--model-repo", default=MODEL_REPO)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--resolved-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    document = build_reference_document(
        model_repo=args.model_repo,
        model_revision=args.model_revision,
        resolved_manifest=args.resolved_manifest,
        batch_size=args.batch_size,
    )
    document.write_json(args.output)
    print(
        json.dumps(
            {
                "reference_run_id": document.reference_run_id,
                "samples": len(document.samples),
                "model_revision": document.source.revision_resolved,
                "model_sha256": document.source.model_file_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
