#!/usr/bin/env python3
"""Bind a fixture generation identity to an already validated candidate receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
BUCKET = re.compile(r"^hf://buckets/([^/]+/[^/]+)/runs/hf-jobs/([^/]+)/([^/]+)/result\.json$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation-id", required=True)
    parser.add_argument("--inspection-id", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--hf-bucket", required=True)
    parser.add_argument("--evaluation-run-id", type=int, required=True)
    parser.add_argument("--evaluation-run-attempt", type=int, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--ack-run-id", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not SHA.fullmatch(args.source_revision):
        raise SystemExit("source revision must be a lowercase 40-hex SHA")
    receipt_bytes = args.candidate_receipt.read_bytes()
    receipt = json.loads(receipt_bytes)
    if receipt.get("conclusion") != "success" or receipt.get("dry_run") is not False:
        raise SystemExit("candidate receipt is not a successful execute receipt")
    if receipt.get("run_id") != args.evaluation_run_id or receipt.get("run_attempt") != args.evaluation_run_attempt:
        raise SystemExit("evaluation run identity does not match candidate receipt")
    result_uri = receipt.get("result_uri")
    match = BUCKET.fullmatch(result_uri or "")
    if not match or match.group(1) != args.hf_bucket:
        raise SystemExit("candidate result_uri does not belong to the requested HF bucket")
    bucket_run_identity = f"runs/hf-jobs/{match.group(2)}/{match.group(3)}"
    binding = {
        "schema_version": 1,
        "generation_id": args.generation_id,
        "inspection_id": args.inspection_id,
        "source_revision": args.source_revision,
        "hf_bucket": args.hf_bucket,
        "status": "completed",
        "evaluation_run_id": args.evaluation_run_id,
        "evaluation_run_attempt": args.evaluation_run_attempt,
        "candidate_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "result_uri": result_uri,
        "bucket_run_identity": bucket_run_identity,
        "ack_run_id": args.ack_run_id,
        "notes": "bound to canonical candidate completion receipt; Bucket identity derived from result_uri",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "bucket_run_identity": bucket_run_identity}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
