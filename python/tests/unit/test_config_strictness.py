from __future__ import annotations

from pathlib import Path

import pytest

from parakeet_onnx.config.errors import ConfigValidationError
from parakeet_onnx.config.models import (
    EvaluationConfig,
    ModelConfig,
    ProviderConfig,
)


PATH = Path("strict.toml")


def test_provider_boolean_does_not_accept_string_truthiness() -> None:
    config = ProviderConfig(
        path=PATH,
        raw={
            "schema_version": 1,
            "provider": {
                "id": "directml",
                "ort_name": "DmlExecutionProvider",
                "enabled": "false",
                "supported_os": ["windows"],
            },
        },
    )
    with pytest.raises(ConfigValidationError, match="provider.enabled must be a boolean"):
        _ = config.enabled


def test_provider_arrays_do_not_coerce_members_to_strings() -> None:
    config = ProviderConfig(
        path=PATH,
        raw={
            "schema_version": 1,
            "provider": {
                "id": "cpu",
                "ort_name": "CPUExecutionProvider",
                "enabled": True,
                "supported_os": ["linux", 42],
            },
        },
    )
    with pytest.raises(ConfigValidationError, match=r"provider\.supported_os\[1\]"):
        _ = config.supported_os


def test_model_identity_does_not_accept_numeric_values() -> None:
    config = ModelConfig(
        path=PATH,
        raw={
            "schema_version": 1,
            "model": {
                "id": "model",
                "family": 7,
                "architecture": "ctc",
                "language": "ja",
            },
            "upstream": {"repo_id": "owner/model"},
            "execution": {
                "supported_providers": ["cpu"],
                "platforms": {"linux": ["cpu"]},
            },
        },
    )
    with pytest.raises(ConfigValidationError, match="model.family must be a non-empty string"):
        _ = config.family


def test_expected_sample_count_rejects_boolean_subclass() -> None:
    config = EvaluationConfig(
        path=PATH,
        raw={
            "schema_version": 1,
            "evaluation": {
                "id": "smoke",
                "manifest": "evaluation/manifests/smoke.jsonl",
                "expected_sample_count": True,
            },
        },
    )
    with pytest.raises(ConfigValidationError, match="must be a positive integer"):
        _ = config.expected_sample_count
