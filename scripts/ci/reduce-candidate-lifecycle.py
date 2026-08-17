#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from candidate_lifecycle_common import STATE_RANK, load_json_object, parse_time


def load(path: str) -> dict:
    try:
        return load_json_object(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid lifecycle candidate {path}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--candidate", action="append", default=[], metavar="SOURCE=PATH")
    parser.add_argument("--output", required=True)
    parser.add_argument("--github-output")
    args = parser.parse_args()

    candidates: list[tuple[object, int, str, str, dict]] = []
    for raw in args.candidate:
        if "=" not in raw:
            raise SystemExit(f"invalid candidate mapping: {raw}")
        source, path = raw.split("=", 1)
        value = load(path)
        if value.get("request_id") != args.request_id:
            raise SystemExit(f"candidate request_id mismatch: {path}")
        state = value.get("state")
        if state not in STATE_RANK:
            raise SystemExit(f"unsupported lifecycle state in {path}: {state}")
        updated_at = value.get("updated_at")
        try:
            observed_at = parse_time(updated_at)
        except (TypeError, ValueError) as error:
            raise SystemExit(f"candidate updated_at is invalid: {path}: {error}") from error
        candidates.append((observed_at, STATE_RANK[state], source, path, value))

    if not candidates:
        raise SystemExit(f"no lifecycle candidates found for request_id={args.request_id}")

    # Current status means the most recently observed lifecycle snapshot. State
    # rank is only a deterministic tie-breaker for equal timestamps; it does not
    # allow an older terminal state to hide a newer retry/rerun observation.
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, source, path, selected = candidates[0]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(selected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write(f"state={selected['state']}\n")
            handle.write(f"source={source}\n")
            handle.write(f"selected_path={path}\n")
            handle.write(f"updated_at={selected['updated_at']}\n")
            handle.write(f"candidate_count={len(candidates)}\n")

    print(
        json.dumps(
            {
                "request_id": args.request_id,
                "state": selected["state"],
                "source": source,
                "updated_at": selected["updated_at"],
                "candidate_count": len(candidates),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
