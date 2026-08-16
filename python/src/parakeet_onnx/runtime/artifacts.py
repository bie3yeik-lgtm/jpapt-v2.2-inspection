from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class CandidateMetadataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateArtifact:
    role: str
    path: Path
    sha256: str | None
    size_bytes: int | None

    def computed_sha256(self) -> str:
        digest = hashlib.sha256()
        with self.path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def verify(self) -> None:
        if not self.path.is_file():
            raise CandidateMetadataError(
                f"candidate artifact for role {self.role!r} does not exist: {self.path}"
            )
        if self.size_bytes is not None and self.path.stat().st_size != self.size_bytes:
            raise CandidateMetadataError(
                f"candidate artifact size mismatch for role {self.role!r}: "
                f"expected={self.size_bytes}, actual={self.path.stat().st_size}"
            )
        if self.sha256 is not None:
            actual = self.computed_sha256()
            if actual.lower() != self.sha256.lower():
                raise CandidateMetadataError(
                    f"candidate artifact SHA-256 mismatch for role {self.role!r}: "
                    f"expected={self.sha256}, actual={actual}"
                )


@dataclass(frozen=True, slots=True)
class CandidateTokenizer:
    kind: str
    path: Path


@dataclass(frozen=True, slots=True)
class CandidateArtifacts:
    root: Path
    metadata_path: Path
    schema_version: int
    candidate_id: str
    decoder: str
    artifact_contract: str
    artifacts: Mapping[str, CandidateArtifact]
    runtime_contract: Mapping[str, Any]
    tokenizer: CandidateTokenizer | None
    features: Mapping[str, bool]

    @classmethod
    def load(
        cls,
        candidate_dir: str | Path,
        *,
        verify_artifacts: bool = True,
    ) -> "CandidateArtifacts":
        root = Path(candidate_dir).expanduser().resolve()
        metadata_path = root / "metadata.json"
        if not metadata_path.is_file():
            raise CandidateMetadataError(f"candidate metadata is missing: {metadata_path}")

        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CandidateMetadataError(
                f"candidate metadata is not valid JSON: {metadata_path}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise CandidateMetadataError("candidate metadata root must be an object")

        schema_version = raw.get("schema_version")
        if schema_version == 2:
            value = cls._load_v2(root=root, metadata_path=metadata_path, raw=raw)
        elif schema_version == 1:
            value = cls._load_v1_compat(root=root, metadata_path=metadata_path, raw=raw)
        else:
            raise CandidateMetadataError(
                f"unsupported candidate metadata schema_version: {schema_version!r}"
            )

        if verify_artifacts:
            for artifact in value.artifacts.values():
                artifact.verify()
            if value.tokenizer is not None and not value.tokenizer.path.exists():
                raise CandidateMetadataError(
                    f"candidate tokenizer/processor path does not exist: {value.tokenizer.path}"
                )
        return value

    @classmethod
    def _load_v2(
        cls,
        *,
        root: Path,
        metadata_path: Path,
        raw: Mapping[str, Any],
    ) -> "CandidateArtifacts":
        candidate_id = _required_string(raw, "candidate_id")
        decoder = _required_string(raw, "decoder")
        artifact_contract = _required_string(raw, "artifact_contract")

        artifact_raw = raw.get("artifacts")
        if not isinstance(artifact_raw, dict) or not artifact_raw:
            raise CandidateMetadataError("artifacts must be a non-empty object")
        artifacts: dict[str, CandidateArtifact] = {}
        for role, entry in artifact_raw.items():
            if not isinstance(role, str) or not role:
                raise CandidateMetadataError("artifact roles must be non-empty strings")
            if not isinstance(entry, dict):
                raise CandidateMetadataError(f"artifact {role!r} must be an object")
            relative = _required_string(entry, "path")
            sha256 = _optional_string(entry, "sha256")
            if sha256 is not None and len(sha256) != 64:
                raise CandidateMetadataError(
                    f"artifact {role!r}.sha256 must be a 64-character digest"
                )
            size_value = entry.get("size_bytes")
            size_bytes: int | None
            if size_value is None:
                size_bytes = None
            elif isinstance(size_value, int) and size_value >= 0:
                size_bytes = size_value
            else:
                raise CandidateMetadataError(
                    f"artifact {role!r}.size_bytes must be a non-negative integer"
                )
            artifacts[role] = CandidateArtifact(
                role=role,
                path=_under_root(root, relative),
                sha256=sha256,
                size_bytes=size_bytes,
            )

        runtime = raw.get("runtime_contract")
        if not isinstance(runtime, dict):
            raise CandidateMetadataError("runtime_contract must be an object")
        runtime_decoder = runtime.get("decoder")
        if runtime_decoder != decoder:
            raise CandidateMetadataError(
                "runtime_contract.decoder must match top-level decoder: "
                f"{runtime_decoder!r} != {decoder!r}"
            )

        tokenizer: CandidateTokenizer | None = None
        tokenizer_raw = raw.get("tokenizer")
        if tokenizer_raw is not None:
            if not isinstance(tokenizer_raw, dict):
                raise CandidateMetadataError("tokenizer must be an object when present")
            tokenizer = CandidateTokenizer(
                kind=_required_string(tokenizer_raw, "kind"),
                path=_under_root(root, _required_string(tokenizer_raw, "path")),
            )

        features_raw = raw.get("features", {})
        if not isinstance(features_raw, dict):
            raise CandidateMetadataError("features must be an object")
        features: dict[str, bool] = {}
        for key, value in features_raw.items():
            if not isinstance(key, str) or not isinstance(value, bool):
                raise CandidateMetadataError("features entries must be boolean values")
            features[key] = value

        return cls(
            root=root,
            metadata_path=metadata_path,
            schema_version=2,
            candidate_id=candidate_id,
            decoder=decoder,
            artifact_contract=artifact_contract,
            artifacts=artifacts,
            runtime_contract=dict(runtime),
            tokenizer=tokenizer,
            features=features,
        )

    @classmethod
    def _load_v1_compat(
        cls,
        *,
        root: Path,
        metadata_path: Path,
        raw: Mapping[str, Any],
    ) -> "CandidateArtifacts":
        """Read the pre-registry CTC shape so existing candidates remain inspectable.

        New candidate writers must emit schema_version=2. The compatibility shape is
        normalized immediately, so runtime/evaluator code never branches on it.
        """

        candidate_id = _required_string(raw, "candidate_id")
        decoder = str(raw.get("decoder", "ctc"))
        primary = _required_string(raw, "primary_artifact")
        sha256 = _optional_string(raw, "artifact_sha256")
        runtime = raw.get("runtime_contract")
        if runtime is None:
            runtime = {"decoder": decoder}
        if not isinstance(runtime, dict):
            raise CandidateMetadataError("runtime_contract must be an object")
        normalized_runtime = dict(runtime)
        normalized_runtime.setdefault("decoder", decoder)
        if decoder == "ctc":
            normalized_runtime.setdefault(
                "io",
                {
                    "primary": {
                        "input": normalized_runtime.get("primary_input"),
                        "length_input": normalized_runtime.get("length_input"),
                        "logits_output": normalized_runtime.get("logits_output"),
                    }
                },
            )
            normalized_runtime.setdefault(
                "decoder_config", {"blank_id": normalized_runtime.get("blank_id")}
            )
        return cls(
            root=root,
            metadata_path=metadata_path,
            schema_version=1,
            candidate_id=candidate_id,
            decoder=decoder,
            artifact_contract="ctc-single-graph-v0" if decoder == "ctc" else f"{decoder}-legacy-v0",
            artifacts={
                "primary": CandidateArtifact(
                    role="primary",
                    path=_under_root(root, primary),
                    sha256=sha256,
                    size_bytes=None,
                )
            },
            runtime_contract=normalized_runtime,
            tokenizer=None,
            features={},
        )

    def artifact(self, role: str) -> CandidateArtifact:
        try:
            return self.artifacts[role]
        except KeyError as exc:
            raise CandidateMetadataError(
                f"candidate artifact role {role!r} is not defined; "
                f"available={sorted(self.artifacts)}"
            ) from exc

    @property
    def primary_artifact(self) -> CandidateArtifact:
        if "primary" in self.artifacts:
            return self.artifacts["primary"]
        if len(self.artifacts) == 1:
            return next(iter(self.artifacts.values()))
        if "encoder" in self.artifacts:
            return self.artifacts["encoder"]
        raise CandidateMetadataError(
            "candidate has multiple artifacts and no primary/encoder role"
        )

    @property
    def bundle_sha256(self) -> str:
        digest = hashlib.sha256()
        for role in sorted(self.artifacts):
            artifact = self.artifacts[role]
            sha = artifact.sha256 or artifact.computed_sha256()
            relative = artifact.path.relative_to(self.root).as_posix()
            digest.update(f"{role}\0{relative}\0{sha}\n".encode("utf-8"))
        return digest.hexdigest()

    def provenance_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "decoder": self.decoder,
            "artifact_contract": self.artifact_contract,
            "bundle_sha256": self.bundle_sha256,
            "artifacts": {
                role: {
                    "path": artifact.path.relative_to(self.root).as_posix(),
                    "sha256": artifact.sha256 or artifact.computed_sha256(),
                    "size_bytes": artifact.path.stat().st_size,
                }
                for role, artifact in sorted(self.artifacts.items())
            },
            "features": dict(self.features),
        }


def _required_string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise CandidateMetadataError(f"{key} must be a non-empty string")
    return item.strip()


def _optional_string(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item.strip():
        raise CandidateMetadataError(f"{key} must be a non-empty string when present")
    return item.strip()


def _under_root(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise CandidateMetadataError(
            f"candidate metadata path escapes candidate root: {relative!r}"
        ) from exc
    return path
