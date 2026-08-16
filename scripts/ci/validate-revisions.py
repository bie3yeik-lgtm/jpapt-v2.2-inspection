#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from parakeet_onnx.hf.revisions import RevisionError, load_revision_bundle


DEFAULT_ROOT = Path(".ci/hf/config/revisions")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the pinned Hugging Face revision documents and their "
            "framework, decoder, and repository identities."
        )
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--expected-development-repo-id")
    parser.add_argument("--expected-upstream-repo-id")
    parser.add_argument("--expected-tokenizer-repo-id")
    parser.add_argument("--expected-framework")
    parser.add_argument("--expected-decoder")
    parser.add_argument("--json", action="store_true")
    return parser


def _expect(
    *,
    actual: str,
    expected: str | None,
    label: str,
) -> None:
    if expected is None:
        return
    if actual != expected:
        raise RevisionError(
            f"{label} mismatch: expected={expected!r}, actual={actual!r}"
        )


def _expect_decoder(
    *,
    supported: tuple[str, ...],
    expected: str,
    label: str,
) -> None:
    if expected not in supported:
        raise RevisionError(
            f"{label} mismatch: expected {expected!r} in {list(supported)!r}"
        )


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.expanduser().resolve()

    try:
        bundle = load_revision_bundle(root)
        reference = bundle.reference

        _expect(
            actual=reference.development_artifact_repo_id,
            expected=args.expected_development_repo_id,
            label="development_artifact.repo_id",
        )
        _expect(
            actual=reference.upstream_repo_id,
            expected=args.expected_upstream_repo_id,
            label="upstream.repo_id",
        )
        _expect(
            actual=reference.tokenizer_repo_id,
            expected=args.expected_tokenizer_repo_id,
            label="tokenizer.repo_id",
        )
        _expect(
            actual=reference.canonical_framework,
            expected=args.expected_framework,
            label="canonical_framework",
        )

        if args.expected_decoder is not None:
            _expect_decoder(
                supported=reference.decoders.supported,
                expected=args.expected_decoder,
                label="reference.json decoder",
            )
            _expect_decoder(
                supported=bundle.evaluation_schema.decoders.supported,
                expected=args.expected_decoder,
                label="evaluation-schema.json decoder",
            )

    except (RevisionError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"ERROR: revision validation failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                bundle.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        reference = bundle.reference
        print("Revision documents are valid.")
        print(f"root: {root}")
        print(f"bundle_sha256: {bundle.sha256}")
        print(
            "development_artifact: "
            f"{reference.development_artifact_repo_id}@"
            f"{reference.development_artifact_revision}"
        )
        print(
            "upstream: "
            f"{reference.upstream_repo_id}@{reference.upstream_revision}"
        )
        print(
            "tokenizer: "
            f"{reference.tokenizer_repo_id}@{reference.tokenizer_revision}"
        )
        print(f"canonical_framework: {reference.canonical_framework}")
        print(
            "reference_decoders: "
            f"{','.join(reference.decoders.supported)}"
        )
        print(
            "evaluation_schema: "
            f"{bundle.evaluation_schema.schema_id}@"
            f"{bundle.evaluation_schema.schema_revision}"
        )
        print(
            "evaluation_decoders: "
            f"{','.join(bundle.evaluation_schema.decoders.supported)}"
        )
        print(f"datasets: {len(bundle.datasets.datasets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
