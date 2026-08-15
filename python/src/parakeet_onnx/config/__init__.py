"""
Configuration subsystem for parakeet-onnx.

This package resolves repository configuration from:

    config/models/
    config/providers/
    config/environments/
    config/evaluation/

into a single typed ResolvedConfig instance.

Typical usage:

    from parakeet_onnx.config import resolve_config

    config = resolve_config(
        model="parakeet-tdt_ctc-0.6b-ja",
        provider="cpu",
        evaluation="parity",
    )

The operating-system environment is automatically detected unless an
explicit environment is supplied.
"""

from .environment import detect_environment_id
from .errors import (
    ConfigError,
    ConfigFileNotFoundError,
    ConfigMergeError,
    ConfigValidationError,
    UnsupportedEnvironmentError,
    UnsupportedProviderError,
)
from .loader import load_toml
from .models import (
    EvaluationConfig,
    ExecutionEnvironmentConfig,
    ModelConfig,
    ProviderConfig,
    ResolvedConfig,
)
from .paths import RepositoryPaths, find_repository_root
from .resolver import ConfigResolver, resolve_config

__all__ = [
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigMergeError",
    "ConfigResolver",
    "ConfigValidationError",
    "EvaluationConfig",
    "ExecutionEnvironmentConfig",
    "ModelConfig",
    "ProviderConfig",
    "RepositoryPaths",
    "ResolvedConfig",
    "UnsupportedEnvironmentError",
    "UnsupportedProviderError",
    "detect_environment_id",
    "find_repository_root",
    "load_toml",
    "resolve_config",
]
