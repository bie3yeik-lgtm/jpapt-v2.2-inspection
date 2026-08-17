#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from candidate_lifecycle_common import (
    STATE_RANK,
    load_json_object,
    observation_sha256,
    request_key,
)


def event_key(snapshot: dict) -> str:
    state = snapshot.get("state")
    if state not in STATE_RANK:
        raise ValueError(f"unsupported lifecycle state: {state}")
    digest = observation_sha256(snapshot)[:16]
    if state in {"planned", "dispatched", "rejected"}:
        run_id = snapshot.get("gateway_run_id") or "unknown"
        return f"gateway-{run_id}-{state}-{digest}"
    if state in {"running", "completed"}:
        run_id = snapshot.get("evaluation_run_id")
        attempt = snapshot.get("evaluation_run_attempt")
        if not isinstance(run_id, int) or run_id < 1:
            raise ValueError(f"{state} requires evaluation_run_id")
        if not isinstance(attempt, int) or attempt < 1:
            raise ValueError(f"{state} requires evaluation_run_attempt")
        return f"evaluation-{run_id}-{attempt}-{state}-{digest}"
    if state == "acknowledged":
        run_id = snapshot.get("evaluation_run_id")
        attempt = snapshot.get("evaluation_run_attempt")
        receiver_run_id = snapshot.get("receiver_run_id")
        if not isinstance(run_id, int) or run_id < 1:
            raise ValueError("acknowledged requires evaluation_run_id")
        if not isinstance(attempt, int) or attempt < 1:
            raise ValueError("acknowledged requires evaluation_run_attempt")
        if not isinstance(receiver_run_id, int) or receiver_run_id < 1:
            raise ValueError("acknowledged requires receiver_run_id")
        return (
            f"evaluation-{run_id}-{attempt}-receiver-{receiver_run_id}-"
            f"acknowledged-{digest}"
        )
    raise ValueError(f"unsupported lifecycle state: {state}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        snapshot = load_json_object(args.snapshot)
        request_id = snapshot.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("request_id is required")
        result = {
            "request_key": request_key(request_id),
            "state": snapshot.get("state"),
            "observation_sha256": observation_sha256(snapshot),
            "event_key": event_key(snapshot),
        }
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid lifecycle snapshot {args.snapshot}: {error}") from error

    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(result["request_key"])
        print(result["state"])
        print(result["event_key"])
        print(result["observation_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
