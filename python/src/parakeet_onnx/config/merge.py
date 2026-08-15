"""
Configuration composition helpers.

Configurations are namespaced rather than blindly deep-merged.

Blind merging would make ownership ambiguous when multiple layers contain
tables such as:

    runtime
    validation
    benchmark

The resolved structure therefore remains:

    model.*
    provider.*
    environment.*
    evaluation.*

Runtime code may then implement explicit precedence rules where required.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .errors import ConfigMergeError
from .models import (
    EvaluationConfig,
    ExecutionEnvironmentConfig,
    ModelConfig,
    ProviderConfig,
)


def compose_config(
    *,
    model: ModelConfig,
    provider: ProviderConfig,
    environment: ExecutionEnvironmentConfig,
    evaluation: EvaluationConfig,
) -> dict[str, Any]:
    """
    Compose source configuration trees into a namespaced resolved tree.
    """

    sources = {
        "model": model.raw,
        "provider": provider.raw,
        "environment": environment.raw,
        "evaluation": evaluation.raw,
    }

    result: dict[str, Any] = {}

    for namespace, raw in sources.items():
        if namespace in result:
            raise ConfigMergeError(
                f"Duplicate configuration namespace: {namespace}"
            )

        result[namespace] = deepcopy(raw)

    result["resolved"] = {
        "model_id": model.id,
        "provider_id": provider.id,
        "environment_id": environment.id,
        "evaluation_id": evaluation.id,
    }

    return result
