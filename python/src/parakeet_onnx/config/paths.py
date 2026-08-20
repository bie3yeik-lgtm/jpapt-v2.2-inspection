"""
Repository path resolution.

Configuration files are repository resources, therefore code must not
assume that the process was launched from the repository root.

Repository root discovery uses known project marker files/directories.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

_REPOSITORY_ROOT_ENV = "PARAKEET_ONNX_REPO_ROOT"

_ROOT_MARKERS = (
    "pyproject.toml",
    "config",
)


def _looks_like_repository_root(path: Path) -> bool:
    """
    Return True when ``path`` appears to be this project's repository root.
    """

    return all((path / marker).exists() for marker in _ROOT_MARKERS)


def find_repository_root(
    start: str | Path | None = None,
) -> Path:
    """
    Locate the repository root.

    Resolution order:

    1. ``start`` if supplied (an explicit caller location is authoritative)
    2. PARAKEET_ONNX_REPO_ROOT when no start is supplied
    3. current working directory
    4. parents of the selected starting location

    Raises:
        ConfigError:
            If no repository root can be found.
    """

    explicit_root = os.environ.get(_REPOSITORY_ROOT_ENV) if start is None else None

    if explicit_root:
        root = Path(explicit_root).expanduser().resolve()

        if not _looks_like_repository_root(root):
            raise ConfigError(f"{_REPOSITORY_ROOT_ENV} does not point to a valid repository root: {root}")

        return root

    candidate = Path(start).expanduser().resolve() if start is not None else Path.cwd().resolve()

    if candidate.is_file():
        candidate = candidate.parent

    for current in (candidate, *candidate.parents):
        if _looks_like_repository_root(current):
            return current

    raise ConfigError(
        f"Unable to locate repository root. Set {_REPOSITORY_ROOT_ENV} explicitly when running outside the repository."
    )


@dataclass(frozen=True, slots=True)
class RepositoryPaths:
    """
    Canonical repository paths used by the configuration subsystem.
    """

    root: Path

    @classmethod
    def discover(
        cls,
        start: str | Path | None = None,
    ) -> RepositoryPaths:
        return cls(
            root=find_repository_root(start),
        )

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def models(self) -> Path:
        return self.config / "models"

    @property
    def providers(self) -> Path:
        return self.config / "providers"

    @property
    def environments(self) -> Path:
        return self.config / "environments"

    @property
    def evaluations(self) -> Path:
        return self.config / "evaluation"

    @property
    def evaluation(self) -> Path:
        return self.root / "evaluation"

    @property
    def manifests(self) -> Path:
        return self.evaluation / "manifests"

    @property
    def cache(self) -> Path:
        return self.root / ".cache"

    @property
    def ci(self) -> Path:
        return self.root / ".ci"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def temporary(self) -> Path:
        return self.root / "tmp"

    def model_config(self, model_id: str) -> Path:
        return self.models / f"{model_id}.toml"

    def provider_config(self, provider_id: str) -> Path:
        return self.providers / f"{provider_id}.toml"

    def environment_config(self, environment_id: str) -> Path:
        return self.environments / f"{environment_id}.toml"

    def evaluation_config(self, evaluation_id: str) -> Path:
        return self.evaluations / f"{evaluation_id}.toml"
