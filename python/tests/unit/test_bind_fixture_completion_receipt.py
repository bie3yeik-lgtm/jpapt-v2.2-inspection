import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "evaluation" / "schemas" / "fixture-generation-receipt.schema.json"
BIND = ROOT / "scripts" / "ci" / "bind-fixture-completion-receipt.py"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_bind_joins_evaluator_evidence(tmp_path: Path) -> None:
    receipt = {
        "schema_version": 1,
        "generation_id": "gen-001",
        "inspection_id": "inspect-gen-001-9-1",
        "source_revision": "f" * 40,
        "hf_bucket": "gawohok7/example-bucket",
        "status": "dispatched",
        "dry_run": False,
        "execute": True,
        "bucket_run_id": None,
        "notes": "waiting",
        "request_id": "gen-001",
        "evaluator_workflow": "candidate-request-gateway.yml",
    }
    lifecycle = {
        "schema_version": 1,
        "request_id": "gen-001",
        "state": "acknowledged",
        "source_repository": "largoyo/Premiere-AutoProcess-Plugin",
        "receipt_repository": "bie3yeik-lgtm/jpapt-v2.2-inspection",
        "orchestrator_repository": "bie3yeik-lgtm/jpapt-v2.2-inspection",
        "gateway_run_id": 11,
        "evaluation_run_id": 22,
        "evaluation_run_attempt": 1,
        "receipt_sha256": "b" * 64,
        "receiver_run_id": 33,
        "updated_at": "2026-08-20T07:40:34.950512Z",
        "request_execution_id": "eval-22-1",
    }
    completion = {
        "request_id": "gen-001",
        "run_id": 22,
        "result_uri": (
            "hf://buckets/gawohok7/example-bucket/runs/"
            "hf-jobs/candidate-000001/smoke-22-1/result.json"
        ),
    }
    receipt_path = tmp_path / "receipt.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    completion_path = tmp_path / "completion.json"
    output_path = tmp_path / "bound.json"
    write_json(receipt_path, receipt)
    write_json(lifecycle_path, lifecycle)
    write_json(completion_path, completion)

    subprocess.run(
        [
            sys.executable,
            str(BIND),
            "--receipt",
            str(receipt_path),
            "--lifecycle",
            str(lifecycle_path),
            "--completion-receipt",
            str(completion_path),
            "--output",
            str(output_path),
        ],
        check=True,
    )
    bound = json.loads(output_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(bound)
    assert bound["status"] == "completed"
    assert bound["inspection_id"] != bound["generation_id"]
    assert bound["request_id"] == "gen-001"
    assert bound["evaluation_run_id"] == 22
    assert bound["receipt_sha256"] == "b" * 64
    assert bound["bucket_run_id"] == "hf-jobs/candidate-000001/smoke-22-1"
    assert bound["lifecycle_state"] == "acknowledged"


def test_bind_rejects_request_id_mismatch(tmp_path: Path) -> None:
    receipt = {
        "schema_version": 1,
        "generation_id": "gen-001",
        "inspection_id": "inspect-gen-001-9-1",
        "source_revision": "f" * 40,
        "hf_bucket": "gawohok7/example-bucket",
        "status": "dispatched",
        "dry_run": False,
        "execute": True,
        "bucket_run_id": None,
        "notes": "waiting",
    }
    lifecycle = {
        "request_id": "other-id",
        "state": "acknowledged",
        "evaluation_run_id": 22,
        "evaluation_run_attempt": 1,
        "receipt_sha256": "b" * 64,
        "gateway_run_id": 11,
    }
    write_json(tmp_path / "receipt.json", receipt)
    write_json(tmp_path / "lifecycle.json", lifecycle)
    result = subprocess.run(
        [
            sys.executable,
            str(BIND),
            "--receipt",
            str(tmp_path / "receipt.json"),
            "--lifecycle",
            str(tmp_path / "lifecycle.json"),
            "--output",
            str(tmp_path / "bound.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not (tmp_path / "bound.json").exists()
    assert "generation_id" in result.stderr
