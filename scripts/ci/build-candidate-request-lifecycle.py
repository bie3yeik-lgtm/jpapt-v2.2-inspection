#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from candidate_lifecycle_common import STATES, parse_time

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_FIELDS = {
    "schema_version",
    "request_id",
    "state",
    "source_repository",
    "receipt_repository",
    "orchestrator_repository",
    "gateway_run_id",
    "evaluation_run_id",
    "evaluation_run_attempt",
    "receipt_sha256",
    "receiver_run_id",
    "updated_at",
}


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def integer_or_none(value: str) -> int | None:
    return int(value) if value else None


def request_key(request_id: str) -> str:
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise SystemExit("request_id is invalid")
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]


def load_json(path: str | None) -> dict | None:
    if not path:
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


def validate(snapshot: dict) -> None:
    if set(snapshot) != EXPECTED_FIELDS:
        missing = sorted(EXPECTED_FIELDS - set(snapshot))
        unknown = sorted(set(snapshot) - EXPECTED_FIELDS)
        raise SystemExit(f"lifecycle fields mismatch: missing={missing}, unknown={unknown}")
    if snapshot.get("schema_version") != 1:
        raise SystemExit("schema_version must be 1")
    request_id = snapshot.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise SystemExit("request_id is invalid")
    if snapshot.get("state") not in STATES:
        raise SystemExit("state is invalid")
    for field in ("source_repository", "receipt_repository", "orchestrator_repository"):
        value = snapshot.get(field)
        if not isinstance(value, str) or not REPOSITORY_RE.fullmatch(value):
            raise SystemExit(f"{field} must use owner/name")
    for field in ("gateway_run_id", "evaluation_run_id", "evaluation_run_attempt", "receiver_run_id"):
        value = snapshot.get(field)
        if value is not None and (not isinstance(value, int) or value < 1):
            raise SystemExit(f"{field} must be null or a positive integer")
    receipt_sha256 = snapshot.get("receipt_sha256")
    if receipt_sha256 is not None and (
        not isinstance(receipt_sha256, str) or not SHA256_RE.fullmatch(receipt_sha256)
    ):
        raise SystemExit("receipt_sha256 is invalid")
    state = snapshot["state"]
    if state in {"dispatched", "rejected"} and snapshot["gateway_run_id"] is None:
        raise SystemExit(f"{state} requires gateway_run_id")
    if state in {"running", "completed", "acknowledged"}:
        if snapshot["evaluation_run_id"] is None or snapshot["evaluation_run_attempt"] is None:
            raise SystemExit(f"{state} requires evaluation run identity")
    if state in {"completed", "acknowledged"} and snapshot["receipt_sha256"] is None:
        raise SystemExit(f"{state} requires receipt_sha256")
    if state == "acknowledged" and snapshot["receiver_run_id"] is None:
        raise SystemExit("acknowledged requires receiver_run_id")
    try:
        parse_time(snapshot.get("updated_at"))
    except (TypeError, ValueError) as error:
        raise SystemExit(f"updated_at is invalid: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", choices=STATES)
    parser.add_argument("--receipt")
    parser.add_argument("--ack")
    parser.add_argument("--rejection")
    parser.add_argument("--output")
    parser.add_argument("--validate")
    parser.add_argument("--request-key")
    args = parser.parse_args()

    if args.request_key:
        print(request_key(args.request_key))
        return 0
    if args.validate:
        snapshot = load_json(args.validate)
        assert snapshot is not None
        validate(snapshot)
        return 0
    if not args.state or not args.output:
        parser.error("--state and --output are required when building a lifecycle snapshot")

    receipt = load_json(args.receipt)
    ack = load_json(args.ack)
    rejection = load_json(args.rejection)
    request_id = env("REQUEST_ID")
    source_repository = env("SOURCE_REPOSITORY")
    receipt_repository = env("RECEIPT_REPOSITORY")
    orchestrator_repository = env("ORCHESTRATOR_REPOSITORY")
    gateway_run_id = integer_or_none(env("GATEWAY_RUN_ID"))
    evaluation_run_id = integer_or_none(env("EVALUATION_RUN_ID"))
    evaluation_run_attempt = integer_or_none(env("EVALUATION_RUN_ATTEMPT"))
    receipt_sha256 = env("RECEIPT_SHA256") or None
    receiver_run_id = integer_or_none(env("RECEIVER_RUN_ID"))

    if receipt:
        request_id = receipt["request_id"]
        source_repository = receipt["source_repository"]
        receipt_repository = receipt["receipt_repository"]
        orchestrator_repository = receipt["orchestrator_repository"]
        evaluation_run_id = receipt["run_id"]
        evaluation_run_attempt = receipt["run_attempt"]
    if ack:
        request_id = ack["request_id"]
        receipt_repository = ack["receipt_repository"]
        orchestrator_repository = ack["orchestrator_repository"]
        evaluation_run_id = ack["evaluation_run_id"]
        evaluation_run_attempt = ack["evaluation_run_attempt"]
        receipt_sha256 = ack["receipt_sha256"]
        receiver_run_id = ack["receiver_run_id"]
        source_repository = source_repository or env("SOURCE_REPOSITORY")
    if rejection:
        request_id = rejection["request_id"]
        source_repository = rejection["source_repository"]
        receipt_repository = rejection["receipt_repository"]
        orchestrator_repository = rejection["orchestrator_repository"]
        gateway_run_id = rejection["gateway_run_id"]

    snapshot = {
        "schema_version": 1,
        "request_id": request_id,
        "state": args.state,
        "source_repository": source_repository,
        "receipt_repository": receipt_repository,
        "orchestrator_repository": orchestrator_repository,
        "gateway_run_id": gateway_run_id,
        "evaluation_run_id": evaluation_run_id,
        "evaluation_run_attempt": evaluation_run_attempt,
        "receipt_sha256": receipt_sha256,
        "receiver_run_id": receiver_run_id,
        "updated_at": env("UPDATED_AT") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    validate(snapshot)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
