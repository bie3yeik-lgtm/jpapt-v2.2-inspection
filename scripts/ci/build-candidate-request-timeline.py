#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from candidate_lifecycle_common import (
    STATE_RANK,
    load_json_object,
    observation_sha256,
    parse_time,
)
from candidate_lifecycle_common import (
    request_key as build_request_key,
)

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
REQUEST_KEY_RE = re.compile(r"^[0-9a-f]{24}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_snapshot(path: str, request_id: str, request_execution_id: str | None = None) -> dict:
    try:
        value = load_json_object(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid lifecycle snapshot {path}: {error}") from error
    if value.get("request_id") != request_id:
        raise SystemExit(
            "lifecycle snapshot request_id mismatch: "
            f"expected={request_id} actual={value.get('request_id')} path={path}"
        )
    if request_execution_id and value.get("request_execution_id") != request_execution_id:
        raise SystemExit(
            "lifecycle snapshot request_execution_id mismatch: "
            f"expected={request_execution_id} actual={value.get('request_execution_id')} path={path}"
        )
    state = value.get("state")
    if state not in STATE_RANK:
        raise SystemExit(f"lifecycle snapshot state is invalid: {state}")
    try:
        parse_time(value.get("updated_at"))
    except (TypeError, ValueError) as error:
        raise SystemExit(f"snapshot updated_at is invalid: {path}: {error}") from error
    return value


def parse_candidate(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise SystemExit("--candidate must use source=path")
    source, path = text.split("=", 1)
    if not source or not path:
        raise SystemExit("--candidate must use non-empty source=path")
    return source, path


def validate_timeline(value: dict) -> None:
    required = {
        "schema_version",
        "request_id",
        "request_key",
        "current_state",
        "event_count",
        "events",
    }
    optional = {"request_execution_id"}
    fields = set(value)
    if required - fields or fields - required - optional:
        raise SystemExit("timeline fields mismatch")
    if value.get("schema_version") != 1:
        raise SystemExit("schema_version must be 1")
    request_id = value.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise SystemExit("request_id is invalid")
    request_execution_id = value.get("request_execution_id")
    if request_execution_id is not None and (
        not isinstance(request_execution_id, str) or not REQUEST_ID_RE.fullmatch(request_execution_id)
    ):
        raise SystemExit("request_execution_id is invalid")
    timeline_request_key = value.get("request_key")
    expected_key = build_request_key(request_id)
    if not isinstance(timeline_request_key, str) or not REQUEST_KEY_RE.fullmatch(timeline_request_key):
        raise SystemExit("request_key is invalid")
    if timeline_request_key != expected_key:
        raise SystemExit("request_key does not match request_id")
    events = value.get("events")
    if not isinstance(events, list) or not events:
        raise SystemExit("events must be a non-empty array")
    if value.get("event_count") != len(events):
        raise SystemExit("event_count does not match events")
    previous_key: tuple[datetime, int, str] | None = None
    seen_hashes: set[str] = set()
    for event in events:
        if not isinstance(event, dict) or set(event) != {
            "observation_sha256",
            "sources",
            "snapshot",
        }:
            raise SystemExit("timeline event fields mismatch")
        digest = event.get("observation_sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise SystemExit("observation_sha256 is invalid")
        if digest in seen_hashes:
            raise SystemExit("duplicate observation_sha256")
        seen_hashes.add(digest)
        sources = event.get("sources")
        if (
            not isinstance(sources, list)
            or not sources
            or not all(isinstance(item, str) and item for item in sources)
            or sources != sorted(set(sources))
        ):
            raise SystemExit("sources must be sorted unique non-empty strings")
        snapshot = event.get("snapshot")
        if not isinstance(snapshot, dict):
            raise SystemExit("snapshot must be object")
        if snapshot.get("request_id") != request_id:
            raise SystemExit("timeline snapshot request_id mismatch")
        if request_execution_id and snapshot.get("request_execution_id") != request_execution_id:
            raise SystemExit("timeline snapshot request_execution_id mismatch")
        state = snapshot.get("state")
        if state not in STATE_RANK:
            raise SystemExit("timeline snapshot state invalid")
        if observation_sha256(snapshot) != digest:
            raise SystemExit("observation_sha256 does not match snapshot")
        try:
            observed_at = parse_time(snapshot.get("updated_at"))
        except (TypeError, ValueError) as error:
            raise SystemExit(f"timeline snapshot updated_at is invalid: {error}") from error
        key = (observed_at, STATE_RANK[state], digest)
        if previous_key is not None and key < previous_key:
            raise SystemExit("events are not ordered")
        previous_key = key
    if value.get("current_state") != events[-1]["snapshot"]["state"]:
        raise SystemExit("current_state does not match latest event")


def build(
    request_id: str,
    request_execution_id: str | None,
    candidates: list[str],
    output: str,
) -> None:
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise SystemExit("request_id is invalid")
    if request_execution_id and not REQUEST_ID_RE.fullmatch(request_execution_id):
        raise SystemExit("request_execution_id is invalid")
    observations: dict[str, dict] = {}
    for candidate in candidates:
        source, path = parse_candidate(candidate)
        snapshot = load_snapshot(path, request_id, request_execution_id)
        digest = observation_sha256(snapshot)
        if digest not in observations:
            observations[digest] = {"snapshot": snapshot, "sources": set()}
        observations[digest]["sources"].add(source)
    if not observations:
        raise SystemExit("at least one --candidate is required")

    ordered = sorted(
        observations.items(),
        key=lambda item: (
            parse_time(item[1]["snapshot"]["updated_at"]),
            STATE_RANK[item[1]["snapshot"]["state"]],
            item[0],
        ),
    )
    events = [
        {
            "observation_sha256": digest,
            "sources": sorted(data["sources"]),
            "snapshot": data["snapshot"],
        }
        for digest, data in ordered
    ]
    timeline = {
        "schema_version": 1,
        "request_id": request_id,
        "request_key": build_request_key(request_id),
        "current_state": events[-1]["snapshot"]["state"],
        "event_count": len(events),
        "events": events,
    }
    if request_execution_id:
        timeline["request_execution_id"] = request_execution_id
    validate_timeline(timeline)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(timeline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(target.read_text(encoding="utf-8"), end="")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-id")
    parser.add_argument("--request-execution-id")
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument("--output")
    parser.add_argument("--validate")
    args = parser.parse_args()
    if args.validate:
        if args.request_id or args.request_execution_id or args.candidate or args.output:
            raise SystemExit("--validate cannot be combined with build arguments")
        try:
            value = load_json_object(args.validate)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise SystemExit(f"invalid timeline file {args.validate}: {error}") from error
        validate_timeline(value)
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0
    if not args.request_id or not args.output:
        raise SystemExit("build mode requires --request-id and --output")
    build(args.request_id, args.request_execution_id, args.candidate, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
