import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "evaluation" / "schemas" / "windows-directml-external-receipt.schema.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_windows_directml_external_receipt_schema_accepts_plan_receipt() -> None:
    schema = load_json(SCHEMA_PATH)
    payload = {
        "schema_version": 1,
        "source_repository": "largoyo/Premiere-AutoProcess-Plugin",
        "source_revision": "b" * 40,
        "hf_bucket": "gawohok7/example-bucket",
        "candidate_id": "candidate-000001",
        "provider_id": "directml",
        "runner_os": "windows",
        "validation_mode": "smoke",
        "status": "planned",
        "dry_run": True,
        "execute": False,
        "linux_hf_jobs_smoke_equivalent": False,
        "hf_target": "parakeet-tdt_ctc-0.6b-ja",
        "notes": "plan-only",
    }
    jsonschema.Draft202012Validator(schema).validate(payload)
