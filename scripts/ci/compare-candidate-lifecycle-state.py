#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from candidate_lifecycle_common import load_json_object, parse_time


def load(path: str) -> dict:
    try:
        return load_json_object(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid lifecycle state {path}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--existing", required=True)
    parser.add_argument("--incoming", required=True)
    args = parser.parse_args()

    existing = load(args.existing)
    incoming = load(args.incoming)
    for field in ("request_id", "state"):
        if existing.get(field) != incoming.get(field):
            raise SystemExit(f"materialized lifecycle {field} mismatch")

    try:
        existing_time = parse_time(existing.get("updated_at"))
        incoming_time = parse_time(incoming.get("updated_at"))
    except (TypeError, ValueError) as error:
        raise SystemExit(f"materialized lifecycle updated_at is invalid: {error}") from error

    should_write = incoming_time >= existing_time
    print("true" if should_write else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
