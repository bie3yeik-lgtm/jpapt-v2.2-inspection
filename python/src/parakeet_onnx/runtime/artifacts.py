from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from parakeet_onnx.config.catalog import (
    AsrCatalog,
    AsrCatalogError,
    DecoderProfile,
    load_repository_catalog,
)
from parakeet_onnx.contracts import (
    ContractError,
    GeneratedArtifact,
    GeneratedCandidateContract,
    GeneratedCatalog,
    GeneratedRuntimeContract,
    GeneratedTokenizer,
)

from .inspection import CandidateInspectionError, inspect_runtime_contract


class CandidateMetadataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateArtifact:
    role: str
    path: Path
    sha256: str
    size_bytes: int

    @classmethod
    def from_file(cls, *, role: str, path: Path) -> "CandidateArtifact":
        if not path.is_file():
            raise CandidateMetadataError(
                f"candidate artifact for role {role!r} does not exist: {path}"
            )
        size_bytes = path.stat().st_size
        if size_bytes <= 0:
            raise CandidateMetadataError(
                f"candidate artifact for role {role!r} must not be empty: {path}"
            )
        return cls(
            role=role,
            path=path,
            sha256=_sha256_file(path),
            size_bytes=size_bytes,
        )

    def verify(self) -> None:
        if not self.path.is_file():
            raise CandidateMetadataError(
                f"candidate artifact for role {self.role!r} does not exist: {self.path}"
            )
        if self.path.stat().st_size != self.size_bytes:
            raise CandidateMetadataError(
                f"candidate artifact size changed for role {self.role!r}: "
                f"expected={self.size_bytes}, actual={self.path.stat().st_size}"
            )
        actual = _sha256_file(self.path)
        if actual.lower() != self.sha256.lower():
            raise CandidateMetadataError(
                f"candidate artifact SHA-256 changed for role {self.role!r}: "
                f"expected={self.sha256}, actual={actual}"
            )


@dataclass(frozen=True, slots=True)
class CandidateTokenizer:
    kind: str
    path: Path


@dataclass(frozen=True, slots=True)
class CandidateArtifacts:
    """One resolved runtime variant from minimal human-authored metadata."""

    root: Path
    metadata_path: Path
    candidate_id: str
    decoder: str
    artifact_contract: str
    artifacts: Mapping[str, CandidateArtifact]
    runtime_contract: Mapping[str, Any]
    tokenizer: CandidateTokenizer | None
    features: Mapping[str, bool]
    profile_set_id: str
    variant: str
    profile_id: str
    catalog_id: str
    catalog_sha256: str

    @classmethod
    def load(
        cls,
        candidate_dir: str | Path,
        *,
        variant: str | None = None,
        verify_artifacts: bool = True,
        repository_root: str | Path | None = None,
        catalog: AsrCatalog | None = None,
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

        repo_root = (
            Path(repository_root).expanduser().resolve()
            if repository_root is not None
            else _discover_repository_root(root)
        )
        _validate_metadata_schema(raw, repo_root)

        if catalog is None:
            try:
                catalog = load_repository_catalog(repo_root)
            except AsrCatalogError as exc:
                raise CandidateMetadataError(str(exc)) from exc

        profile_set_id = _required_string(raw, "profile_set")
        try:
            profile_set = catalog.profile_set(profile_set_id)
        except AsrCatalogError as exc:
            raise CandidateMetadataError(str(exc)) from exc

        variants_raw = _required_mapping(raw, "variants")
        unknown_variants = sorted(set(variants_raw) - set(profile_set.variants))
        if unknown_variants:
            raise CandidateMetadataError(
                f"candidate contains variants not defined by profile set "
                f"{profile_set_id!r}: {unknown_variants}"
            )
        selected_variant = variant or profile_set.default_variant
        if selected_variant not in profile_set.variants:
            raise CandidateMetadataError(
                f"variant {selected_variant!r} is not defined by profile set "
                f"{profile_set_id!r}; available={sorted(profile_set.variants)}"
            )
        variant_raw = variants_raw.get(selected_variant)
        if not isinstance(variant_raw, Mapping):
            raise CandidateMetadataError(
                f"candidate does not provide selected variant {selected_variant!r}; "
                f"available={sorted(str(key) for key in variants_raw)}"
            )

        profile_id = profile_set.profile_id_for(selected_variant)
        profile = catalog.decoder_profile(profile_id)
        artifacts = _load_artifacts(root, variant_raw.get("artifacts"))
        _validate_artifact_roles(profile, artifacts)
        tokenizer = _load_tokenizer(root, variant_raw.get("tokenizer"), profile)
        candidate_id = _candidate_id(root)

        try:
            runtime_contract = inspect_runtime_contract(
                root=root,
                decoder=profile.decoder,
                artifacts={role: artifact.path for role, artifact in artifacts.items()},
                tokenizer_path=tokenizer.path if tokenizer is not None else None,
            )
        except CandidateInspectionError as exc:
            raise CandidateMetadataError(str(exc)) from exc

        value = cls(
            root=root,
            metadata_path=metadata_path,
            candidate_id=candidate_id,
            decoder=profile.decoder,
            artifact_contract=profile.artifact_contract,
            artifacts=artifacts,
            runtime_contract=runtime_contract,
            tokenizer=tokenizer,
            features=dict(profile.features),
            profile_set_id=profile_set_id,
            variant=selected_variant,
            profile_id=profile_id,
            catalog_id=catalog.catalog_id,
            catalog_sha256=catalog.sha256,
        )
        if verify_artifacts:
            for artifact in value.artifacts.values():
                artifact.verify()
            if value.tokenizer is not None and not value.tokenizer.path.exists():
                raise CandidateMetadataError(
                    f"candidate tokenizer/processor path does not exist: {value.tokenizer.path}"
                )
        value.generated_contract().validate()
        return value

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
            relative = artifact.path.relative_to(self.root).as_posix()
            digest.update(f"{role}\0{relative}\0{artifact.sha256}\n".encode("utf-8"))
        return digest.hexdigest()

    def generated_contract(self) -> GeneratedCandidateContract:
        io = self.runtime_contract.get("io")
        decoder_config = self.runtime_contract.get("decoder_config")
        input_kind = self.runtime_contract.get("input_kind")
        runtime_decoder = self.runtime_contract.get("decoder")
        if not isinstance(io, Mapping):
            raise CandidateMetadataError("runtime contract io must be an object")
        if not isinstance(decoder_config, Mapping):
            raise CandidateMetadataError("runtime contract decoder_config must be an object")
        if not isinstance(input_kind, str) or not input_kind:
            raise CandidateMetadataError("runtime contract input_kind must be a non-empty string")
        if not isinstance(runtime_decoder, str) or not runtime_decoder:
            raise CandidateMetadataError("runtime contract decoder must be a non-empty string")

        contract = GeneratedCandidateContract(
            schema_version=1,
            candidate_root=str(self.root),
            candidate_id=self.candidate_id,
            profile_set=self.profile_set_id,
            variant=self.variant,
            profile=self.profile_id,
            decoder=self.decoder,
            artifact_contract=self.artifact_contract,
            catalog=GeneratedCatalog(id=self.catalog_id, sha256=self.catalog_sha256),
            bundle_sha256=self.bundle_sha256,
            artifacts={
                role: GeneratedArtifact(
                    path=artifact.path.relative_to(self.root).as_posix(),
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                )
                for role, artifact in sorted(self.artifacts.items())
            },
            tokenizer=(
                GeneratedTokenizer(
                    kind=self.tokenizer.kind,
                    path=self.tokenizer.path.relative_to(self.root).as_posix(),
                )
                if self.tokenizer is not None
                else None
            ),
            features=dict(self.features),
            runtime_contract=GeneratedRuntimeContract(
                decoder=runtime_decoder,
                input_kind=input_kind,
                io=dict(io),
                decoder_config=dict(decoder_config),
            ),
        )
        try:
            contract.validate()
        except ContractError as exc:
            raise CandidateMetadataError(str(exc)) from exc
        return contract


def _validate_metadata_schema(raw: Mapping[str, Any], repository_root: Path) -> None:
    schema_path = repository_root / "evaluation" / "schemas" / "candidate-metadata.schema.json"
    if not schema_path.is_file():
        raise CandidateMetadataError(f"candidate metadata schema is missing: {schema_path}")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateMetadataError(f"invalid candidate metadata schema: {exc}") from exc
    errors = sorted(
        Draft202012Validator(schema).iter_errors(raw),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(item) for item in first.absolute_path) or "$"
        raise CandidateMetadataError(
            f"candidate metadata schema violation at {location}: {first.message}"
        )


def _load_artifacts(root: Path, raw: object) -> dict[str, CandidateArtifact]:
    if not isinstance(raw, Mapping) or not raw:
        raise CandidateMetadataError("artifacts must be a non-empty object")
    artifacts: dict[str, CandidateArtifact] = {}
    for role, relative in raw.items():
        if not isinstance(role, str) or not role:
            raise CandidateMetadataError("artifact roles must be non-empty strings")
        if not isinstance(relative, str) or not relative.strip():
            raise CandidateMetadataError(f"artifact {role!r} path must be a non-empty string")
        path = _under_root(root, relative.strip())
        artifacts[role] = CandidateArtifact.from_file(role=role, path=path)
    return artifacts


def _validate_artifact_roles(
    profile: DecoderProfile, artifacts: Mapping[str, CandidateArtifact]
) -> None:
    missing = sorted(set(profile.required_artifact_roles) - set(artifacts))
    if missing:
        raise CandidateMetadataError(
            f"decoder profile {profile.profile_id!r} is missing required artifact roles: {missing}"
        )
    allowed = set(profile.required_artifact_roles) | set(profile.optional_artifact_roles)
    unexpected = sorted(set(artifacts) - allowed)
    if unexpected:
        raise CandidateMetadataError(
            f"decoder profile {profile.profile_id!r} has unexpected artifact roles: {unexpected}"
        )


def _load_tokenizer(
    root: Path, raw: object, profile: DecoderProfile
) -> CandidateTokenizer | None:
    explicit: Path | None = None
    if raw is not None:
        if not isinstance(raw, str) or not raw.strip():
            raise CandidateMetadataError("tokenizer must be a non-empty path string when present")
        explicit = _under_root(root, raw.strip())
        if not explicit.exists():
            raise CandidateMetadataError(f"candidate tokenizer path does not exist: {explicit}")

    path = explicit or _discover_tokenizer(root, profile.tokenizer_kind)
    if path is None:
        raise CandidateMetadataError(
            f"decoder profile {profile.profile_id!r} requires tokenizer kind "
            f"{profile.tokenizer_kind!r}; declare tokenizer path or use a conventional layout"
        )
    return CandidateTokenizer(kind=profile.tokenizer_kind, path=path)


def _discover_tokenizer(root: Path, kind: str) -> Path | None:
    if kind == "vocabulary":
        for relative in (
            "tokenizer/vocabulary.json",
            "vocabulary.json",
            "tokenizer/vocab.json",
            "vocab.json",
            "tokenizer/tokens.json",
            "tokens.json",
        ):
            path = root / relative
            if path.is_file():
                return path.resolve()
        return None
    if kind == "transformers_processor":
        for relative in ("tokenizer", "processor", "."):
            path = (root / relative).resolve()
            if path.is_dir() and any(
                (path / name).is_file()
                for name in ("preprocessor_config.json", "tokenizer_config.json", "config.json")
            ):
                return path
        return None
    return None


def _candidate_id(root: Path) -> str:
    marker = root / ".candidate-id"
    if marker.is_file():
        value = marker.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = root.name.strip()
    if not value:
        raise CandidateMetadataError("candidate identity cannot be derived from an empty root name")
    return value


def _required_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise CandidateMetadataError(f"{key} must be an object")
    return item


def _required_string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise CandidateMetadataError(f"{key} must be a non-empty string")
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _discover_repository_root(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / "config" / "asr-catalog.json").is_file():
            return parent
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        if (parent / "config" / "asr-catalog.json").is_file():
            return parent
    raise CandidateMetadataError(
        "could not locate config/asr-catalog.json; pass repository_root explicitly"
    )
