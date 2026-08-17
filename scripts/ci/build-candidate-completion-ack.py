#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from candidate_protocol_common import parse_rfc3339_time

EVENT_TYPE = "jpapt.candidate-completion-ack"
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_FIELDS = {
    "schema_version",
    "request_id",
    "receipt_sha256",
    "receipt_repository",
    "orchestrator_repository",
    "evaluation_run_id",
    "evaluation_run_attempt",
    "receiver_repository",
    "receiver_run_id",
    "receiver_run_attempt",
    "receiver_run_url",
    "accepted_at",
}


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def canonical_receipt_sha256(receipt: dict) -> str:
    payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_ack(ack: dict) -> None:
    if set(ack) != EXPECTED_FIELDS:
        missing = sorted(EXPECTED_FIELDS - set(ack))
        unknown = sorted(set(ack) - EXPECTED_FIELDS)
        raise SystemExit(f"ack fields mismatch: missing={missing}, unknown={unknown}")
    if ack.get("schema_version") != 1:
        raise SystemExit("schema_version must be 1")
    request_id = ack.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise SystemExit("request_id is invalid")
    receipt_sha256 = ack.get("receipt_sha256")
    if not isinstance(receipt_sha256, str) or not SHA256_RE.fullmatch(receipt_sha256):
        raise SystemExit("receipt_sha256 is invalid")
    for field in ("receipt_repository", "orchestrator_repository", "receiver_repository"):
        value = ack.get(field)
        if not isinstance(value, str) or not REPOSITORY_RE.fullmatch(value):
            raise SystemExit(f"{field} must use owner/name")
    for field in ("evaluation_run_id", "evaluation_run_attempt", "receiver_run_id", "receiver_run_attempt"):
        value = ack.get(field)
        if not isinstance(value, int) or value < 1:
            raise SystemExit(f"{field} must be a positive integer")
    receiver_run_url = ack.get("receiver_run_url")
    if not isinstance(receiver_run_url, str) or not receiver_run_url.startswith("https://"):
        raise SystemExit("receiver_run_url is invalid")
    try:
        parse_rfc3339_time(ack.get("accepted_at"), "accepted_at")
    except ValueError as error:
        raise SystemExit(str(error)) from error


def load_json(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt")
    parser.add_argument("--receipt-sha")
    parser.add_argument("--ack")
    parser.add_argument("--dispatch-body")
    parser.add_argument("--validate")
    args = parser.parse_args()
    if args.validate:
        validate_ack(load_json(args.validate))
        return 0
    if args.receipt_sha:
        print(canonical_receipt_sha256(load_json(args.receipt_sha)))
        return 0
    if not args.receipt or not args.ack or not args.dispatch_body:
        parser.error("--receipt, --ack, and --dispatch-body are required when building an acknowledgement")

    receipt = load_json(args.receipt)
    for field in ("request_id", "receipt_repository", "orchestrator_repository", "run_id", "run_attempt"):
        if field not in receipt:
            raise SystemExit(f"receipt is missing {field}")

    ack = {
        "schema_version": 1,
        "request_id": receipt["request_id"],
        "receipt_sha256": canonical_receipt_sha256(receipt),
        "receipt_repository": receipt["receipt_repository"],
        "orchestrator_repository": receipt["orchestrator_repository"],
        "evaluation_run_id": receipt["run_id"],
        "evaluation_run_attempt": receipt["run_attempt"],
        "receiver_repository": env("RECEIVER_REPOSITORY"),
        "receiver_run_id": int(env("RECEIVER_RUN_ID")),
        "receiver_run_attempt": int(env("RECEIVER_RUN_ATTEMPT", "1")),
        "receiver_run_url": env("RECEIVER_RUN_URL"),
        "accepted_at": env("ACCEPTED_AT") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    validate_ack(ack)
    ack_path = Path(args.ack)
    dispatch_path = Path(args.dispatch_body)
    ack_path.parent.mkdir(parents=True, exist_ok=True)
    dispatch_path.parent.mkdir(parents=True, exist_ok=True)
    ack_path.write_text(json.dumps(ack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    dispatch_path.write_text(
        json.dumps({"event_type": EVENT_TYPE, "client_payload": ack}, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(ack_path.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
