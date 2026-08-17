#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def parse_time(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


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
    for label, value in (("existing", existing), ("incoming", incoming)):
        updated_at = value.get("updated_at")
        if not isinstance(updated_at, str) or not updated_at:
            raise SystemExit(f"{label} updated_at is required")

    should_write = parse_time(incoming["updated_at"]) >= parse_time(existing["updated_at"])
    print("true" if should_write else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
