from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from parakeet_onnx.evaluation.schema import (
    EvaluationSchemaError,
    EvaluationSchemaRegistry,
)
from parakeet_onnx.nemo import MODEL_FILE, MODEL_REPO, NORMALIZATION_ID

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _reference() -> dict[str, object]:
    return {
        "schema_version": 1,
        "reference_run_id": "nemo-000000000000-ctc-111111111111",
        "source": {
            "repo_id": MODEL_REPO,
            "revision_resolved": "0" * 40,
            "model_file": MODEL_FILE,
            "model_file_sha256": "1" * 64,
            "library": "nemo",
            "language": "ja",
            "license": "cc-by-4.0",
        },
        "decoder": "ctc",
        "normalization": NORMALIZATION_ID,
        "samples": [
            {
                "id": "sample-1",
                "audio_sha256": _sha("audio"),
                "reference_text": "日本語",
                "text": "日本語",
                "normalized_text": "日本語",
            }
        ],
    }


def test_registry_loads_all_nemo_schemas() -> None:
    registry = EvaluationSchemaRegistry(REPOSITORY_ROOT)
    for schema_name in (
        registry.NEMO_ONNX_VALIDATION,
        registry.NEMO_REFERENCE_QUALITY,
        registry.NEMO_ONNX_QUALITY,
    ):
        schema = registry.load_schema(schema_name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_registry_applies_typed_reference_semantics() -> None:
    registry = EvaluationSchemaRegistry(REPOSITORY_ROOT)
    value = _reference()
    registry.validate_nemo_reference_quality(value)
    samples = value["samples"]
    assert isinstance(samples, list)
    first = samples[0]
    assert isinstance(first, dict)
    first["normalized_text"] = "wrong"
    with pytest.raises(EvaluationSchemaError, match="semantic contract failed"):
        registry.validate_nemo_reference_quality(value)
