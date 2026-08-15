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
            "Validate the three pinned Hugging Face revision documents, "
            "including framework/decoder compatibility."
        )
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--expected-model-id")
    parser.add_argument("--expected-framework")
    parser.add_argument("--expected-decoder")
    parser.add_argument(
        "--allow-legacy-metadata",
        action="store_true",
        help=(
            "Allow framework/decoder identity to be absent from older "
            "revision documents. Present values must still match."
        ),
    )
    parser.add_argument("--json", action="store_true")
    return parser


def _expect(
    *,
    actual: str | None,
    expected: str | None,
    label: str,
    allow_missing: bool = False,
) -> None:
    if expected is None:
        return
    if actual is None and allow_missing:
        print(
            f"WARN: {label} is absent from legacy revision metadata; "
            f"target expects {expected!r}.",
            file=sys.stderr,
        )
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
    allow_missing: bool,
) -> None:
    if not supported and allow_missing:
        print(
            f"WARN: {label} is absent from legacy revision metadata; "
            f"target expects {expected!r}.",
            file=sys.stderr,
        )
        return
    if expected not in supported:
        raise RevisionError(
            f"{label} mismatch: expected {expected!r} in {list(supported)!r}"
        )


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.expanduser().resolve()

    try:
        bundle = load_revision_bundle(root)
        _expect(
            actual=bundle.reference.model_id,
            expected=args.expected_model_id,
            label="model_id",
        )
        _expect(
            actual=bundle.reference.canonical_framework,
            expected=args.expected_framework,
            label="canonical_framework",
            allow_missing=args.allow_legacy_metadata,
        )

        if args.expected_decoder is not None:
            _expect_decoder(
                supported=bundle.reference.decoders.supported,
                expected=args.expected_decoder,
                label="reference.json decoder",
                allow_missing=args.allow_legacy_metadata,
            )
            _expect_decoder(
                supported=bundle.evaluation_schema.decoders.supported,
                expected=args.expected_decoder,
                label="evaluation-schema.json decoder",
                allow_missing=args.allow_legacy_metadata,
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
        print("Revision documents are valid.")
        print(f"root: {root}")
        print(f"bundle_sha256: {bundle.sha256}")
        print(
            f"model: {bundle.reference.model_id}@"
            f"{bundle.reference.model_revision}"
        )
        print(
            "canonical_framework: "
            f"{bundle.reference.canonical_framework or '<unspecified>'}"
        )
        print(
            "reference_decoders: "
            f"{','.join(bundle.reference.decoders.supported) or '<unspecified>'}"
        )
        print(
            "evaluation_schema: "
            f"{bundle.evaluation_schema.schema_id}@"
            f"{bundle.evaluation_schema.schema_revision}"
        )
        print(
            "evaluation_decoders: "
            f"{','.join(bundle.evaluation_schema.decoders.supported) or '<unspecified>'}"
        )
        print(f"datasets: {len(bundle.datasets.datasets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
