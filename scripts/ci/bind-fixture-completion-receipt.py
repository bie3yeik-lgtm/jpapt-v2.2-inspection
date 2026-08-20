#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUNS_URI_RE = re.compile(r"/runs/(.+?)(?:/result\.json)?$")

IDENTITY_REQUIRED = {
    "schema_version",
    "generation_id",
    "inspection_id",
    "source_revision",
    "hf_bucket",
    "status",
    "dry_run",
    "execute",
}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SystemExit(f"expected integer, got {value!r}")
    return value


def bucket_run_id_from_result_uri(result_uri: str | None) -> str | None:
    if not result_uri:
        return None
    match = RUNS_URI_RE.search(result_uri)
    if not match:
        return None
    return match.group(1).removesuffix("/result.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--lifecycle", required=True)
    parser.add_argument("--completion-receipt")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    receipt = load_object(Path(args.receipt))
    missing = sorted(IDENTITY_REQUIRED - set(receipt))
    if missing:
        raise SystemExit(f"fixture receipt missing fields: {missing}")
    if receipt.get("schema_version") != 1:
        raise SystemExit("fixture receipt schema_version must be 1")

    lifecycle = load_object(Path(args.lifecycle))
    request_id = lifecycle.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise SystemExit("lifecycle request_id is invalid")
    if request_id != receipt["generation_id"]:
        raise SystemExit(
            "lifecycle request_id must equal fixture generation_id: "
            f"{request_id} != {receipt['generation_id']}"
        )

    lifecycle_state = lifecycle.get("state")
    if lifecycle_state != "acknowledged":
        raise SystemExit(
            f"lifecycle state must be acknowledged, got {lifecycle_state!r}"
        )

    receipt_sha256 = lifecycle.get("receipt_sha256")
    if not isinstance(receipt_sha256, str) or not SHA256_RE.fullmatch(receipt_sha256):
        raise SystemExit("lifecycle receipt_sha256 is invalid")

    evaluation_run_id = optional_int(lifecycle.get("evaluation_run_id"))
    if evaluation_run_id is None:
        raise SystemExit("lifecycle evaluation_run_id is required")

    result_uri = None
    if args.completion_receipt:
        completion = load_object(Path(args.completion_receipt))
        if completion.get("request_id") != request_id:
            raise SystemExit("completion receipt request_id must equal generation_id")
        if completion.get("run_id") != evaluation_run_id:
            raise SystemExit(
                "completion receipt run_id must equal lifecycle evaluation_run_id"
            )
        uri = completion.get("result_uri")
        result_uri = uri if isinstance(uri, str) and uri else None

    bound = dict(receipt)
    bound["status"] = "completed"
    bound["request_id"] = request_id
    bound["gateway_run_id"] = optional_int(lifecycle.get("gateway_run_id"))
    bound["evaluation_run_id"] = evaluation_run_id
    bound["evaluation_run_attempt"] = optional_int(
        lifecycle.get("evaluation_run_attempt")
    )
    bound["receipt_sha256"] = receipt_sha256
    bound["result_uri"] = result_uri
    bound["lifecycle_state"] = lifecycle_state
    bound["evaluator_workflow"] = "candidate-request-gateway.yml"
    bound["bucket_run_id"] = bucket_run_id_from_result_uri(result_uri) or receipt.get(
        "bucket_run_id"
    )
    bound["notes"] = (
        "fixture identities bound to canonical candidate evaluator completion; "
        "HF Jobs/Bucket completion came from candidate-package-evaluate-v2"
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(bound, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
