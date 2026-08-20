import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "evaluation" / "schemas" / "provenance.schema.json"
FIXTURE_ROOT = ROOT / "evaluation" / "provenance" / "fixtures"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_provenance_schema_accepts_incomplete_and_complete_fixtures() -> None:
    schema = load_json(SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)

    for name in ("incomplete.json", "complete.json"):
        validator.validate(load_json(FIXTURE_ROOT / name))


@pytest.mark.parametrize(
    "name",
    ("invalid-missing-origin.json", "invalid-path.json", "invalid-automation.json"),
)
def test_provenance_schema_rejects_invalid_fixtures(name: str) -> None:
    schema = load_json(SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)

    with pytest.raises(jsonschema.ValidationError):
        validator.validate(load_json(FIXTURE_ROOT / name))
