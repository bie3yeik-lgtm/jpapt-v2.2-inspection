#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from parakeet_onnx.config.catalog import load_repository_catalog


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write config runtime.json without duplicating decoder semantics."
    )
    parser.add_argument("--profile-set", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args()

    catalog = load_repository_catalog(args.repository_root)
    catalog.profile_set(args.profile_set)  # validate reference
    value = {
        "schema_version": 1,
        "catalog": {
            "id": catalog.catalog_id,
            "sha256": catalog.sha256,
        },
        "profile_set": args.profile_set,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
