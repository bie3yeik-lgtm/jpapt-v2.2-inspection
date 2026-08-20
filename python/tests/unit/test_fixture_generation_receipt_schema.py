import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "evaluation" / "schemas" / "fixture-generation-receipt.schema.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_receipt(**overrides: object) -> dict:
    payload = {
        "schema_version": 1,
        "generation_id": "gen-001",
        "inspection_id": "inspect-gen-001-1-1",
        "source_revision": "f" * 40,
        "hf_bucket": "gawohok7/example-bucket",
        "status": "planned",
        "dry_run": True,
        "execute": False,
        "bucket_run_id": None,
        "notes": "plan-only",
    }
    payload.update(overrides)
    return payload


def test_fixture_generation_receipt_schema_accepts_plan_receipt() -> None:
    schema = load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema).validate(valid_receipt())


def test_fixture_generation_receipt_schema_rejects_invalid_status() -> None:
    schema = load_json(SCHEMA_PATH)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(
            valid_receipt(status="success")
        )


def test_fixture_generation_receipt_schema_accepts_completed_binding() -> None:
    schema = load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema).validate(
        valid_receipt(
            status="completed",
            dry_run=False,
            execute=True,
            request_id="gen-001",
            gateway_run_id=1,
            evaluation_run_id=2,
            evaluation_run_attempt=1,
            receipt_sha256="a" * 64,
            result_uri=(
                "hf://buckets/gawohok7/example-bucket/runs/"
                "hf-jobs/candidate-000001/smoke-2-1/result.json"
            ),
            bucket_run_id="hf-jobs/candidate-000001/smoke-2-1",
            lifecycle_state="acknowledged",
            evaluator_workflow="candidate-request-gateway.yml",
            notes="bound",
        )
    )
