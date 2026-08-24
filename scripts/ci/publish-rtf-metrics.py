#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_url


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--metrics", type=Path, required=True)
    p.add_argument("--repo-id", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--job-id", default="")
    p.add_argument("--output-receipt", type=Path, required=True)
    args = p.parse_args()
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        raise SystemExit("HF_TOKEN is required to publish CPU RTF metrics")
    payload = json.loads(args.metrics.read_text(encoding="utf-8"))
    if payload.get("run_id") != args.run_id or payload.get("status") != "completed":
        raise SystemExit("only the completed metrics for the requested run may be published")
    digest = hashlib.sha256(args.metrics.read_bytes()).hexdigest()
    commit = HfApi(token=token).upload_file(
        path_or_fileobj=str(args.metrics),
        path_in_repo=args.path,
        repo_id=args.repo_id,
        repo_type="dataset",
        commit_message=f"Publish CPU RTF metrics {args.run_id}",
    )
    uri = hf_hub_url(args.repo_id, filename=args.path, repo_type="dataset", revision=commit.oid)
    receipt = {
        "schema_version": 1,
        "run_id": args.run_id,
        "status": "completed",
        "job_id": args.job_id or None,
        "result_uri": uri,
        "result_sha256": digest,
        "metrics_uri": uri,
        "metrics_sha256": digest,
        "result_repo_id": args.repo_id,
        "result_revision": commit.oid,
        "result_path": args.path,
    }
    args.output_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RTF_RESULT_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
