#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

EVENT_TYPE = "jpapt.candidate-rejected"
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
REASON_CODE = "REQUEST_NORMALIZATION_OR_RESOLUTION_FAILED"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def validate(value: dict) -> None:
    expected = {
        "schema_version",
        "request_id",
        "source_repository",
        "receipt_repository",
        "orchestrator_repository",
        "reason_code",
        "gateway_run_id",
        "gateway_run_attempt",
        "gateway_run_url",
        "rejected_at",
    }
    if set(value) != expected:
        raise SystemExit("rejection fields mismatch")
    if value.get("schema_version") != 1:
        raise SystemExit("schema_version must be 1")
    request_id = value.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise SystemExit("request_id is invalid")
    for field in ("source_repository", "receipt_repository", "orchestrator_repository"):
        repo = value.get(field)
        if not isinstance(repo, str) or not REPOSITORY_RE.fullmatch(repo):
            raise SystemExit(f"{field} must use owner/name")
    if value.get("reason_code") != REASON_CODE:
        raise SystemExit("reason_code is invalid")
    for field in ("gateway_run_id", "gateway_run_attempt"):
        number = value.get(field)
        if not isinstance(number, int) or number < 1:
            raise SystemExit(f"{field} must be a positive integer")
    if not isinstance(value.get("gateway_run_url"), str) or not value["gateway_run_url"].startswith("https://"):
        raise SystemExit("gateway_run_url is invalid")
    if not isinstance(value.get("rejected_at"), str) or "T" not in value["rejected_at"]:
        raise SystemExit("rejected_at is invalid")


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("rejection must be a JSON object")
    validate(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rejection")
    parser.add_argument("--dispatch-body")
    parser.add_argument("--validate")
    args = parser.parse_args()

    if args.validate:
        print(json.dumps(load(args.validate), indent=2, ensure_ascii=False))
        return 0
    if not args.rejection or not args.dispatch_body:
        parser.error("--rejection and --dispatch-body are required")

    source_repository = env("SOURCE_REPOSITORY")
    receipt_repository = env("RECEIPT_REPOSITORY") or source_repository
    request_id = env("REQUEST_ID") or f"gh-{env('GITHUB_RUN_ID')}-{env('GITHUB_RUN_ATTEMPT', '1')}"
    rejection = {
        "schema_version": 1,
        "request_id": request_id,
        "source_repository": source_repository,
        "receipt_repository": receipt_repository,
        "orchestrator_repository": env("ORCHESTRATOR_REPOSITORY"),
        "reason_code": REASON_CODE,
        "gateway_run_id": int(env("GATEWAY_RUN_ID")),
        "gateway_run_attempt": int(env("GATEWAY_RUN_ATTEMPT", "1")),
        "gateway_run_url": env("GATEWAY_RUN_URL"),
        "rejected_at": env("REJECTED_AT") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    validate(rejection)

    rejection_path = Path(args.rejection)
    dispatch_path = Path(args.dispatch_body)
    rejection_path.parent.mkdir(parents=True, exist_ok=True)
    dispatch_path.parent.mkdir(parents=True, exist_ok=True)
    rejection_path.write_text(json.dumps(rejection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    dispatch_path.write_text(
        json.dumps({"event_type": EVENT_TYPE, "client_payload": rejection}, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(rejection_path.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
