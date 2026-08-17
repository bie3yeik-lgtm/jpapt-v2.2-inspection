#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


def allowed_repositories(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def validate_receipt_binding(receipt: dict, receiver_repository: str, allowed: set[str]) -> None:
    if receipt.get("receipt_repository") != receiver_repository:
        raise SystemExit(
            "receipt_repository does not match receiver repository: "
            f"{receipt.get('receipt_repository')} != {receiver_repository}"
        )
    orchestrator = receipt.get("orchestrator_repository")
    if orchestrator == receiver_repository:
        return
    if not allowed:
        raise SystemExit(
            "external orchestrator is not allowed: configure "
            "JPAPT_ORCHESTRATOR_REPOSITORIES"
        )
    if orchestrator not in allowed:
        raise SystemExit(f"orchestrator_repository is not allowlisted: {orchestrator}")


def validate_ack_binding(receipt: dict, ack: dict, orchestrator_repository: str) -> None:
    checks = {
        "orchestrator_repository": orchestrator_repository,
        "request_id": receipt.get("request_id"),
        "receipt_repository": receipt.get("receipt_repository"),
        "evaluation_run_id": receipt.get("run_id"),
        "evaluation_run_attempt": receipt.get("run_attempt"),
        "receiver_repository": receipt.get("receipt_repository"),
    }
    for field, expected in checks.items():
        actual = ack.get(field)
        if actual != expected:
            raise SystemExit(f"ACK binding mismatch for {field}: {actual!r} != {expected!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--ack")
    parser.add_argument("--receiver-repository")
    parser.add_argument("--orchestrator-repository")
    parser.add_argument("--allowed-orchestrators", default="")
    args = parser.parse_args()

    receipt = load(args.receipt)
    if args.ack:
        if not args.orchestrator_repository:
            parser.error("--orchestrator-repository is required with --ack")
        validate_ack_binding(receipt, load(args.ack), args.orchestrator_repository)
    else:
        if not args.receiver_repository:
            parser.error("--receiver-repository is required without --ack")
        validate_receipt_binding(
            receipt,
            args.receiver_repository,
            allowed_repositories(args.allowed_orchestrators),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
