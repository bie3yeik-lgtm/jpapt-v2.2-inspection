"""
Typed RunContext models.

The serialized structure should remain language-neutral so that a future
Rust implementation can read and emit the same run-context.json contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """
    Identity of the actual deployment artifact used for inference.
    """

    path: str
    sha256: str
    size_bytes: int

    candidate_id: str | None = None
    artifact_role: str | None = None


@dataclass(frozen=True, slots=True)
class GitIdentity:
    repository: str | None
    commit: str | None
    ref: str | None
    dirty: bool | None


@dataclass(frozen=True, slots=True)
class HostIdentity:
    os: str
    architecture: str

    hostname: str | None

    python_version: str
    implementation: str

    is_wsl: bool

    github_runner_os: str | None = None
    github_runner_arch: str | None = None
    github_run_id: str | None = None
    github_run_attempt: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """
    Runtime implementation metadata.

    implementation:
        python
        rust

    backend:
        onnxruntime
        nemo
        transformers
    """

    implementation: str
    backend: str

    backend_version: str | None

    provider_id: str
    provider_ort_name: str

    provider_available: bool | None = None


@dataclass(frozen=True, slots=True)
class RunContext:
    """
    Complete immutable description of a single evaluation run.
    """

    schema_version: int

    run_id: str
    created_at: str

    config_identity: str

    model_id: str
    environment_id: str
    provider_id: str
    evaluation_id: str

    artifact: ArtifactIdentity

    git: GitIdentity
    host: HostIdentity
    runtime: RuntimeIdentity

    revisions: dict[str, Any]

    config: dict[str, Any]

    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(
        self,
        *,
        indent: int = 2,
    ) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )

    def write_json(
        self,
        path: str | Path,
    ) -> None:
        destination = Path(path)

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_text(
            self.to_json() + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def utc_timestamp(
        value: datetime,
    ) -> str:
        return value.isoformat()
