#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from parakeet_onnx.config.catalog import load_repository_catalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    sub = parser.add_subparsers(dest="command", required=True)

    profile = sub.add_parser("profile")
    profile.add_argument("profile_id")
    profile.add_argument(
        "field", choices=["decoder", "artifact_contract", "tokenizer_kind"]
    )

    profile_set = sub.add_parser("profile-set")
    profile_set.add_argument("profile_set_id")
    profile_set.add_argument("--variant")
    profile_set.add_argument(
        "field",
        choices=[
            "profile_id",
            "decoder",
            "artifact_contract",
            "tokenizer_kind",
            "default_variant",
        ],
    )

    fingerprint = sub.add_parser("fingerprint")
    fingerprint.add_argument("field", choices=["catalog_id", "sha256"])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    catalog = load_repository_catalog(args.repository_root)
    if args.command == "fingerprint":
        print(getattr(catalog, args.field))
        return 0
    if args.command == "profile":
        profile = catalog.decoder_profile(args.profile_id)
        print(getattr(profile, args.field))
        return 0

    profile_set = catalog.profile_set(args.profile_set_id)
    if args.field == "default_variant":
        print(profile_set.default_variant)
        return 0
    profile_id = profile_set.profile_id_for(args.variant)
    if args.field == "profile_id":
        print(profile_id)
        return 0
    profile = catalog.decoder_profile(profile_id)
    print(getattr(profile, args.field))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
