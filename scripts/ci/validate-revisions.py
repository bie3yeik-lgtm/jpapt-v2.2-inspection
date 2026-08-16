#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from parakeet_onnx.config.catalog import load_repository_catalog
from parakeet_onnx.hf.revisions import RevisionError, load_revision_bundle


DEFAULT_ROOT = Path(".ci/hf/config/revisions")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate pinned Hugging Face revision documents, repository identities, "
            "and the normalized runtime profile lock."
        )
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--expected-development-repo-id")
    parser.add_argument("--expected-upstream-repo-id")
    parser.add_argument("--expected-tokenizer-repo-id")
    parser.add_argument("--expected-framework")
    parser.add_argument("--expected-profile-set")
    parser.add_argument("--runtime-variant")
    parser.add_argument("--expected-runtime-profile")
    parser.add_argument("--expected-decoder")
    parser.add_argument("--json", action="store_true")
    return parser


def _expect(*, actual: str, expected: str | None, label: str) -> None:
    if expected is not None and actual != expected:
        raise RevisionError(
            f"{label} mismatch: expected={expected!r}, actual={actual!r}"
        )


def _expect_decoder(
    *, supported: tuple[str, ...], expected: str, label: str
) -> None:
    if expected not in supported:
        raise RevisionError(
            f"{label} mismatch: expected {expected!r} in {list(supported)!r}"
        )


def _discover_repository_root(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / "config" / "asr-catalog.json").is_file():
            return parent
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        if (parent / "config" / "asr-catalog.json").is_file():
            return parent
    raise RevisionError("could not locate repository config/asr-catalog.json")


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

        if bundle.runtime is not None:
            _expect(
                actual=bundle.runtime.profile_set_id,
                expected=args.expected_profile_set,
                label="runtime.profile_set",
            )
            catalog = load_repository_catalog(_discover_repository_root(root))
            variant, profile_id, decoder = bundle.runtime.resolve_variant(
                args.runtime_variant, catalog=catalog
            )
            _expect(
                actual=profile_id,
                expected=args.expected_runtime_profile,
                label=f"runtime.variant[{variant}].profile",
            )
            _expect(
                actual=decoder,
                expected=args.expected_decoder,
                label=f"runtime.variant[{variant}].decoder",
            )
        elif args.expected_profile_set or args.expected_runtime_profile or args.runtime_variant:
            raise RevisionError(
                "runtime profile expectations were supplied, but selected config is a "
                "legacy three-file config without runtime.json"
            )

        if args.expected_decoder is not None:
            _expect_decoder(
                supported=reference.decoders.supported,
                expected=args.expected_decoder,
                label="resolved reference decoder set",
            )
            _expect_decoder(
                supported=bundle.evaluation_schema.decoders.supported,
                expected=args.expected_decoder,
                label="resolved evaluation decoder set",
            )

    except (RevisionError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"ERROR: revision validation failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                bundle.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
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
        print(f"upstream: {reference.upstream_repo_id}@{reference.upstream_revision}")
        print(
            f"tokenizer: {reference.tokenizer_repo_id}@{reference.tokenizer_revision}"
        )
        print(f"canonical_framework: {reference.canonical_framework}")
        if bundle.runtime is not None:
            print(f"runtime_profile_set: {bundle.runtime.profile_set_id}")
            print(f"runtime_variants: {','.join(bundle.runtime.variants)}")
            print(f"runtime_default_variant: {bundle.runtime.default_variant}")
        else:
            print("runtime_profile_set: legacy")
        print(f"resolved_decoders: {','.join(reference.decoders.supported)}")
        print(
            "evaluation_schema: "
            f"{bundle.evaluation_schema.schema_id}@"
            f"{bundle.evaluation_schema.schema_revision}"
        )
        print(f"datasets: {len(bundle.datasets.datasets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
