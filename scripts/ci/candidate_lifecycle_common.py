from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from candidate_protocol_common import parse_rfc3339_time

STATES = (
    "planned",
    "dispatched",
    "running",
    "rejected",
    "completed",
    "acknowledged",
)
STATE_RANK = {state: rank for rank, state in enumerate(STATES)}


def parse_time(value: str) -> datetime:
    return parse_rfc3339_time(value, "updated_at")


def load_json_object(path: str | Path) -> dict:
    source = Path(path)
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{source} must contain a JSON object")
    return value


def canonical_bytes(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def observation_sha256(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def request_key(request_id: str) -> str:
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]
