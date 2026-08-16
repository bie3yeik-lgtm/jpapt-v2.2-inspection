from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import os
import platform
from pathlib import Path
import socket
import subprocess
from typing import Any, Mapping
import uuid

from parakeet_onnx.config import ResolvedConfig
from parakeet_onnx.config.environment import is_wsl
from parakeet_onnx.contracts import (
    ArtifactIdentity,
    ConfigSnapshot,
    ContractError,
    GitIdentity,
    HostIdentity,
    RunContext,
    RuntimeIdentity,
    RUN_CONTEXT_SCHEMA_VERSION,
    reject_nulls,
)
from parakeet_onnx.hf.revisions import RevisionBundle
from parakeet_onnx.runtime.artifacts import CandidateArtifacts


def _run_git(repository_root: Path, *args: str, allow_empty: bool = False) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ContractError(
            f"unable to resolve git identity with {' '.join(args)!r}"
        ) from exc
    value = result.stdout.strip()
    if not value and not allow_empty:
        raise ContractError(f"git {' '.join(args)} returned an empty identity")
    return value


def _git_identity(repository_root: Path) -> GitIdentity:
    commit = os.environ.get("GITHUB_SHA") or _run_git(repository_root, "rev-parse", "HEAD")
    ref = (
        os.environ.get("GITHUB_REF")
        or _run_git(repository_root, "symbolic-ref", "--short", "-q", "HEAD")
    )
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        repository = _run_git(repository_root, "config", "--get", "remote.origin.url")
    dirty_value = _run_git(
        repository_root,
        "status",
        "--porcelain",
        "--untracked-files=no",
        allow_empty=True,
    )
    identity = GitIdentity(
        repository=repository,
        commit=commit,
        ref=ref,
        dirty=bool(dirty_value),
    )
    identity.validate()
    return identity


def _package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _runtime_identity(
    config: ResolvedConfig,
    *,
    implementation: str,
    backend_version: str | None,
    provider_available: bool,
) -> RuntimeIdentity:
    version = backend_version
    if implementation == "python" and version is None:
        version = _package_version("onnxruntime") or _package_version("onnxruntime-gpu")
    if not version:
        raise ContractError(
            "runtime backend version is required; refusing an unknown execution identity"
        )
    value = RuntimeIdentity(
        implementation=implementation,
        backend="onnxruntime",
        backend_version=version,
        provider_id=config.provider.id,
        provider_ort_name=config.provider.ort_name,
        provider_available=provider_available,
    )
    value.validate()
    return value


def _host_identity() -> HostIdentity:
    value = HostIdentity(
        os=platform.system(),
        architecture=platform.machine(),
        hostname=socket.gethostname(),
        python_version=platform.python_version(),
        implementation=platform.python_implementation(),
        is_wsl=is_wsl(),
        github_runner_os=os.environ.get("RUNNER_OS") or "local",
        github_runner_arch=os.environ.get("RUNNER_ARCH") or "local",
        github_run_id=os.environ.get("GITHUB_RUN_ID") or "local",
        github_run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT") or "local",
    )
    value.validate()
    return value


def _candidate_contract(candidate: CandidateArtifacts) -> dict[str, Any]:
    value = candidate.provenance_dict()
    value["schema_version"] = 1
    value["candidate_root"] = str(candidate.root)
    if value.get("tokenizer") is None:
        value.pop("tokenizer", None)
    reject_nulls(value, "$.metadata.candidate")
    return value


def _config_snapshot(config: ResolvedConfig) -> ConfigSnapshot:
    def relative(path: Path) -> str:
        try:
            return path.relative_to(config.repository_root).as_posix()
        except ValueError:
            return path.as_posix()

    value = ConfigSnapshot(
        identity=config.identity,
        sources={
            "model": relative(config.model.path),
            "provider": relative(config.provider.path),
            "environment": relative(config.environment.path),
            "evaluation": relative(config.evaluation.path),
        },
        resolved=config.merged,
    )
    value.validate()
    return value


def _make_run_id(
    *,
    config: ResolvedConfig,
    candidate_sha256: str,
    timestamp: datetime,
) -> str:
    safe_model_id = config.model.id.replace("/", "-").replace("_", "-")
    return (
        f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-"
        f"{safe_model_id}-{config.environment.id}-{config.provider.id}-"
        f"{config.evaluation.id}-{candidate_sha256[:8]}-{uuid.uuid4().hex[:8]}"
    )


class RunContextBuilder:
    def __init__(self, *, config: ResolvedConfig, revisions: RevisionBundle) -> None:
        self.config = config
        self.revisions = revisions

    def build(
        self,
        *,
        candidate: CandidateArtifacts,
        runtime_implementation: str = "python",
        runtime_backend_version: str | None = None,
        provider_available: bool = False,
        metadata: Mapping[str, Any] | None = None,
        run_id: str | None = None,
    ) -> RunContext:
        if candidate.profile_set_id != self.revisions.runtime.profile_set_id:
            raise ContractError(
                "candidate profile_set does not match revision runtime profile_set"
            )
        primary = candidate.primary_artifact
        created = datetime.now(timezone.utc)
        extra = dict(metadata or {})
        if "candidate" in extra:
            raise ContractError(
                "metadata.candidate is generated by the builder and cannot be overridden"
            )
        reject_nulls(extra, "$.metadata")

        context = RunContext(
            schema_version=RUN_CONTEXT_SCHEMA_VERSION,
            run_id=run_id
            or _make_run_id(
                config=self.config,
                candidate_sha256=primary.sha256,
                timestamp=created,
            ),
            created_at=created.isoformat(),
            config_identity=self.config.identity,
            model_id=self.config.model.id,
            environment_id=self.config.environment.id,
            provider_id=self.config.provider.id,
            evaluation_id=self.config.evaluation.id,
            artifact=ArtifactIdentity(
                path=self._logical_artifact_path(primary.path),
                sha256=primary.sha256,
                size_bytes=primary.size_bytes,
                candidate_id=candidate.candidate_id,
                artifact_role=primary.role,
            ),
            git=_git_identity(self.config.repository_root),
            host=_host_identity(),
            runtime=_runtime_identity(
                self.config,
                implementation=runtime_implementation,
                backend_version=runtime_backend_version,
                provider_available=provider_available,
            ),
            revisions=self.revisions.snapshot(),
            config=_config_snapshot(self.config),
            metadata={
                "candidate": _candidate_contract(candidate),
                "runtime_variant": candidate.variant,
                "runtime_profile": candidate.profile_id,
                **extra,
            },
        )
        context.validate()
        return context

    def _logical_artifact_path(self, artifact: Path) -> str:
        try:
            return artifact.relative_to(self.config.repository_root).as_posix()
        except ValueError:
            return artifact.as_posix()


def build_run_context(
    *,
    config: ResolvedConfig,
    revisions: RevisionBundle,
    candidate: CandidateArtifacts,
    runtime_implementation: str = "python",
    runtime_backend_version: str | None = None,
    provider_available: bool = False,
    metadata: Mapping[str, Any] | None = None,
    run_id: str | None = None,
) -> RunContext:
    return RunContextBuilder(config=config, revisions=revisions).build(
        candidate=candidate,
        runtime_implementation=runtime_implementation,
        runtime_backend_version=runtime_backend_version,
        provider_available=provider_available,
        metadata=metadata,
        run_id=run_id,
    )
