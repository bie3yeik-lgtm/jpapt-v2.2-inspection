from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def test_expected_schema_accepts_uninitialized_repository_file() -> None:
    root = Path(__file__).resolve().parents[3]

    schema_path = root / "evaluation" / "schemas" / "expected.schema.json"
    expected_path = root / "evaluation" / "expected" / "smoke.json"

    if not schema_path.exists() or not expected_path.exists():
        return

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    errors = list(Draft202012Validator(schema).iter_errors(expected))

    assert errors == []
