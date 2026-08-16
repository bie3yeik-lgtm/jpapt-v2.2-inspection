"""
RunContext builder.

This layer binds:

    ResolvedConfig
        +
    RevisionBundle
        +
    candidate artifact
        +
    Git/runtime/host metadata

into one serializable RunContext.

No inference is performed here.
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import os
import platform
from pathlib import Path
import socket
import subprocess
from typing import Any
import uuid

from parakeet_onnx.config import ResolvedConfig
from parakeet_onnx.config.environment import is_wsl
from parakeet_onnx.hf.revisions import RevisionBundle
from parakeet_onnx.hf.snapshot import normalized_revision_snapshot

from .hashing import sha256_file
from .models import (
    RUN_CONTEXT_SCHEMA_VERSION,
    ArtifactIdentity,
    GitIdentity,
    HostIdentity,
    RunContext,
    RuntimeIdentity,
)


def _run_git(
    repository_root: Path,
    *args: str,
) -> str | None:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                *args,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )

    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
    ):
        return None

    value = result.stdout.strip()

    return value or None


def _detect_git_identity(
    repository_root: Path,
) -> GitIdentity:
    commit = (
        os.environ.get("GITHUB_SHA")
        or _run_git(
            repository_root,
            "rev-parse",
            "HEAD",
        )
    )

    ref = (
        os.environ.get("GITHUB_REF")
        or _run_git(
            repository_root,
            "symbolic-ref",
            "--short",
            "-q",
            "HEAD",
        )
    )

    repository = (
        os.environ.get("GITHUB_REPOSITORY")
        or _detect_git_remote(repository_root)
    )

    dirty = _detect_git_dirty(
        repository_root
    )

    return GitIdentity(
        repository=repository,
        commit=commit,
        ref=ref,
        dirty=dirty,
    )


def _detect_git_remote(
    repository_root: Path,
) -> str | None:
    value = _run_git(
        repository_root,
        "config",
        "--get",
        "remote.origin.url",
    )

    return value


def _detect_git_dirty(
    repository_root: Path,
) -> bool | None:
    value = _run_git(
        repository_root,
        "status",
        "--porcelain",
    )

    if value is None:
        return None

    return bool(value)


def _package_version(
    package_name: str,
) -> str | None:
    try:
        return importlib.metadata.version(
            package_name
        )

    except importlib.metadata.PackageNotFoundError:
        return None


def _detect_runtime_identity(
    config: ResolvedConfig,
) -> RuntimeIdentity:
    ort_version = _package_version(
        "onnxruntime"
    )

    if ort_version is None:
        ort_version = _package_version(
            "onnxruntime-gpu"
        )

    return RuntimeIdentity(
        implementation="python",
        backend="onnxruntime",
        backend_version=ort_version,
        provider_id=config.provider.id,
        provider_ort_name=(
            config.provider.ort_name
        ),
        provider_available=None,
    )


def _detect_host_identity() -> HostIdentity:
    return HostIdentity(
        os=platform.system(),
        architecture=platform.machine(),
        hostname=socket.gethostname(),
        python_version=platform.python_version(),
        implementation=platform.python_implementation(),
        is_wsl=is_wsl(),
        github_runner_os=os.environ.get(
            "RUNNER_OS"
        ),
        github_runner_arch=os.environ.get(
            "RUNNER_ARCH"
        ),
        github_run_id=os.environ.get(
            "GITHUB_RUN_ID"
        ),
        github_run_attempt=os.environ.get(
            "GITHUB_RUN_ATTEMPT"
        ),
    )


def _make_run_id(
    *,
    config: ResolvedConfig,
    candidate_sha256: str,
    timestamp: datetime,
) -> str:
    """
    Produce a globally unique but still human-readable run ID.

    Example:

        20260816T021000Z-parakeet-...-macos-coreml-a1b2c3d4
    """

    timestamp_part = timestamp.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    candidate_short = candidate_sha256[:8]

    random_short = uuid.uuid4().hex[:8]

    safe_model_id = (
        config.model.id
        .replace("/", "-")
        .replace("_", "-")
    )

    return (
        f"{timestamp_part}-"
        f"{safe_model_id}-"
        f"{config.environment.id}-"
        f"{config.provider.id}-"
        f"{config.evaluation.id}-"
        f"{candidate_short}-"
        f"{random_short}"
    )


class RunContextBuilder:
    """
    Construct RunContext objects.
    """

    def __init__(
        self,
        *,
        config: ResolvedConfig,
        revisions: RevisionBundle,
    ) -> None:
        self.config = config
        self.revisions = revisions

    def build(
        self,
        *,
        candidate_path: str | Path,
        candidate_id: str | None = None,
        artifact_role: str | None = None,
        metadata: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> RunContext:
        candidate = (
            Path(candidate_path)
            .expanduser()
            .resolve()
        )

        if not candidate.is_file():
            raise FileNotFoundError(
                f"Candidate artifact does not exist: "
                f"{candidate}"
            )

        candidate_sha256 = sha256_file(
            candidate
        )

        created = datetime.now(
            timezone.utc
        )

        final_run_id = (
            run_id
            or _make_run_id(
                config=self.config,
                candidate_sha256=candidate_sha256,
                timestamp=created,
            )
        )

        artifact = ArtifactIdentity(
            path=self._logical_artifact_path(
                candidate
            ),
            sha256=candidate_sha256,
            size_bytes=candidate.stat().st_size,
            candidate_id=candidate_id,
            artifact_role=artifact_role,
        )

        return RunContext(
            schema_version=RUN_CONTEXT_SCHEMA_VERSION,
            run_id=final_run_id,
            created_at=created.isoformat(),
            config_identity=(
                self.config.identity
            ),
            model_id=self.config.model.id,
            environment_id=(
                self.config.environment.id
            ),
            provider_id=(
                self.config.provider.id
            ),
            evaluation_id=(
                self.config.evaluation.id
            ),
            artifact=artifact,
            git=_detect_git_identity(
                self.config.repository_root
            ),
            host=_detect_host_identity(),
            runtime=_detect_runtime_identity(
                self.config
            ),
            revisions=normalized_revision_snapshot(self.revisions),
            config=self._serialize_config(),
            metadata=dict(metadata or {}),
        )

    def _logical_artifact_path(
        self,
        artifact: Path,
    ) -> str:
        """
        Prefer repository-relative paths where possible.

        Absolute CI temp paths are not useful as durable identities.
        """

        try:
            relative = artifact.relative_to(
                self.config.repository_root
            )

            return relative.as_posix()

        except ValueError:
            return artifact.as_posix()

    def _serialize_config(
        self,
    ) -> dict[str, Any]:
        """
        Include configuration identity and source file paths.

        The full merged config is retained because the run must be
        reproducible even if future defaults change.
        """

        return {
            "identity": self.config.identity,
            "sources": {
                "model": self._relative_path(
                    self.config.model.path
                ),
                "provider": self._relative_path(
                    self.config.provider.path
                ),
                "environment": self._relative_path(
                    self.config.environment.path
                ),
                "evaluation": self._relative_path(
                    self.config.evaluation.path
                ),
            },
            "resolved": self.config.merged,
        }

    def _relative_path(
        self,
        path: Path,
    ) -> str:
        try:
            return path.relative_to(
                self.config.repository_root
            ).as_posix()

        except ValueError:
            return path.as_posix()


def build_run_context(
    *,
    config: ResolvedConfig,
    revisions: RevisionBundle,
    candidate_path: str | Path,
    candidate_id: str | None = None,
    artifact_role: str | None = None,
    metadata: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> RunContext:
    """
    Convenience API.
    """

    return RunContextBuilder(
        config=config,
        revisions=revisions,
    ).build(
        candidate_path=candidate_path,
        candidate_id=candidate_id,
        artifact_role=artifact_role,
        metadata=metadata,
        run_id=run_id,
    )
