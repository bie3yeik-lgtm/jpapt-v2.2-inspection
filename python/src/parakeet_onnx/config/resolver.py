"""
High-level configuration resolver.

The resolver:

1. Detects or accepts an execution environment.
2. Loads model configuration.
3. Loads Execution Provider configuration.
4. Loads evaluation-suite configuration.
5. Validates cross-configuration compatibility.
6. Produces a ResolvedConfig.

No model files, datasets, HF Bucket resources, or ONNX sessions are loaded
here. This module resolves configuration only.
"""

from __future__ import annotations

from pathlib import Path

from .environment import (
    detect_environment_id,
    normalize_environment_id,
)
from .errors import (
    ConfigValidationError,
    UnsupportedProviderError,
)
from .loader import load_toml
from .merge import compose_config
from .models import (
    EvaluationConfig,
    ExecutionEnvironmentConfig,
    ModelConfig,
    ProviderConfig,
    ResolvedConfig,
)
from .paths import RepositoryPaths


class ConfigResolver:
    """
    Repository configuration resolver.
    """

    def __init__(
        self,
        repository_root: str | Path | None = None,
    ) -> None:
        if repository_root is None:
            self.paths = RepositoryPaths.discover()
        else:
            root = Path(repository_root).expanduser().resolve()

            self.paths = RepositoryPaths(
                root=root,
            )

    def load_model(
        self,
        model_id: str,
    ) -> ModelConfig:
        path = self.paths.model_config(model_id)

        config = ModelConfig(
            path=path,
            raw=load_toml(path),
        )

        if config.id != model_id:
            raise ConfigValidationError(
                "Model filename and model.id disagree: "
                f"filename={model_id!r}, model.id={config.id!r}",
                path=path,
            )

        return config

    def load_provider(
        self,
        provider_id: str,
    ) -> ProviderConfig:
        path = self.paths.provider_config(provider_id)

        config = ProviderConfig(
            path=path,
            raw=load_toml(path),
        )

        if config.id != provider_id:
            raise ConfigValidationError(
                "Provider filename and provider.id disagree: "
                f"filename={provider_id!r}, provider.id={config.id!r}",
                path=path,
            )

        return config

    def load_environment(
        self,
        environment_id: str,
    ) -> ExecutionEnvironmentConfig:
        normalized_id = normalize_environment_id(
            environment_id
        )

        path = self.paths.environment_config(
            normalized_id
        )

        config = ExecutionEnvironmentConfig(
            path=path,
            raw=load_toml(path),
        )

        if config.id != normalized_id:
            raise ConfigValidationError(
                "Environment filename and environment.id disagree: "
                f"filename={normalized_id!r}, "
                f"environment.id={config.id!r}",
                path=path,
            )

        return config

    def load_evaluation(
        self,
        evaluation_id: str,
    ) -> EvaluationConfig:
        path = self.paths.evaluation_config(
            evaluation_id
        )

        config = EvaluationConfig(
            path=path,
            raw=load_toml(path),
        )

        if config.id != evaluation_id:
            raise ConfigValidationError(
                "Evaluation filename and evaluation.id disagree: "
                f"filename={evaluation_id!r}, "
                f"evaluation.id={config.id!r}",
                path=path,
            )

        return config

    def resolve(
        self,
        *,
        model: str,
        provider: str,
        evaluation: str,
        environment: str | None = None,
    ) -> ResolvedConfig:
        """
        Resolve all execution configuration.

        Args:
            model:
                Model configuration ID.

                Example:
                    ``parakeet-tdt_ctc-0.6b-ja``

            provider:
                Execution Provider ID.

                One of:
                    cpu
                    cuda
                    directml
                    coreml

            evaluation:
                Evaluation suite.

                One of:
                    smoke
                    parity
                    full

            environment:
                Optional explicit environment.

                When omitted, the host OS is detected.

        Returns:
            ResolvedConfig
        """

        environment_id = (
            normalize_environment_id(environment)
            if environment is not None
            else detect_environment_id()
        )

        model_config = self.load_model(model)
        provider_config = self.load_provider(provider)
        environment_config = self.load_environment(
            environment_id
        )
        evaluation_config = self.load_evaluation(
            evaluation
        )

        self._validate_compatibility(
            model=model_config,
            provider=provider_config,
            environment=environment_config,
            evaluation=evaluation_config,
        )

        merged = compose_config(
            model=model_config,
            provider=provider_config,
            environment=environment_config,
            evaluation=evaluation_config,
        )

        return ResolvedConfig(
            repository_root=self.paths.root,
            model=model_config,
            provider=provider_config,
            environment=environment_config,
            evaluation=evaluation_config,
            merged=merged,
        )

    def _validate_compatibility(
        self,
        *,
        model: ModelConfig,
        provider: ProviderConfig,
        environment: ExecutionEnvironmentConfig,
        evaluation: EvaluationConfig,
    ) -> None:
        """
        Validate cross-file constraints.
        """

        if not provider.enabled:
            raise ConfigValidationError(
                f"Provider is disabled: {provider.id}",
                path=provider.path,
            )

        if provider.id not in model.supported_providers:
            raise UnsupportedProviderError(
                provider.id,
                environment.id,
            )

        model_environment_providers = (
            model.providers_for_environment(
                environment.id
            )
        )

        if provider.id not in model_environment_providers:
            raise UnsupportedProviderError(
                provider.id,
                environment.id,
            )

        if environment.id not in provider.supported_os:
            raise UnsupportedProviderError(
                provider.id,
                environment.id,
            )

        supported_eval_environments = evaluation.get(
            "ci.supported_environments",
            [],
        )

        if supported_eval_environments:
            if not isinstance(
                supported_eval_environments,
                list,
            ):
                raise ConfigValidationError(
                    "ci.supported_environments must be an array.",
                    path=evaluation.path,
                )

            if (
                environment.id
                not in supported_eval_environments
            ):
                raise ConfigValidationError(
                    "Evaluation suite does not support "
                    f"environment={environment.id!r}: "
                    f"evaluation={evaluation.id!r}",
                    path=evaluation.path,
                )

        manifest = self.paths.root / evaluation.manifest

        if not manifest.is_file():
            raise ConfigValidationError(
                f"Evaluation manifest does not exist: {manifest}",
                path=evaluation.path,
            )


def resolve_config(
    *,
    model: str,
    provider: str,
    evaluation: str,
    environment: str | None = None,
    repository_root: str | Path | None = None,
) -> ResolvedConfig:
    """
    Convenience function for resolving project configuration.

    Example:

        config = resolve_config(
            model="parakeet-tdt_ctc-0.6b-ja",
            provider="cpu",
            evaluation="smoke",
        )
    """

    resolver = ConfigResolver(
        repository_root=repository_root,
    )

    return resolver.resolve(
        model=model,
        provider=provider,
        evaluation=evaluation,
        environment=environment,
    )
