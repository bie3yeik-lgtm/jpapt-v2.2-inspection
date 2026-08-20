from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from parakeet_onnx.contracts import (
    ContractError,
    GeneratedArtifact,
    GeneratedCandidateContract,
    GeneratedCatalog,
    GeneratedRuntimeContract,
    GeneratedTokenizer,
    reject_nulls,
)


def _object(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def _exact(
    value: Mapping[str, Any],
    *,
    name: str,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        raise ContractError(f"{name} is missing required fields: {missing!r}")
    if unknown:
        raise ContractError(f"{name} contains unknown fields: {unknown!r}")


def _string(value: Mapping[str, Any], key: str, *, name: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ContractError(f"{name}.{key} must be a non-empty string")
    return item


def _positive_int(value: Mapping[str, Any], key: str, *, name: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool) or item <= 0:
        raise ContractError(f"{name}.{key} must be a positive integer")
    return item


def parse_generated_candidate_contract(value: Any) -> GeneratedCandidateContract:
    reject_nulls(value, "$.metadata.candidate")
    raw = _object(value, name="metadata.candidate")
    _exact(
        raw,
        name="metadata.candidate",
        required={
            "schema_version",
            "candidate_root",
            "candidate_id",
            "profile_set",
            "variant",
            "profile",
            "decoder",
            "artifact_contract",
            "catalog",
            "bundle_sha256",
            "artifacts",
            "features",
            "runtime_contract",
        },
        optional={"tokenizer"},
    )
    schema_version = raw["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ContractError("metadata.candidate.schema_version must be an integer")

    catalog_raw = _object(raw["catalog"], name="metadata.candidate.catalog")
    _exact(
        catalog_raw,
        name="metadata.candidate.catalog",
        required={"id", "sha256"},
    )

    artifacts_raw = _object(raw["artifacts"], name="metadata.candidate.artifacts")
    if not artifacts_raw:
        raise ContractError("metadata.candidate.artifacts must not be empty")
    artifacts: dict[str, GeneratedArtifact] = {}
    for role, item in artifacts_raw.items():
        if not isinstance(role, str) or not role.strip():
            raise ContractError("metadata.candidate artifact roles must be non-empty strings")
        name = f"metadata.candidate.artifacts.{role}"
        artifact_raw = _object(item, name=name)
        _exact(
            artifact_raw,
            name=name,
            required={"path", "sha256", "size_bytes"},
        )
        artifacts[role] = GeneratedArtifact(
            path=_string(artifact_raw, "path", name=name),
            sha256=_string(artifact_raw, "sha256", name=name),
            size_bytes=_positive_int(artifact_raw, "size_bytes", name=name),
        )

    tokenizer: GeneratedTokenizer | None = None
    if "tokenizer" in raw:
        tokenizer_raw = _object(raw["tokenizer"], name="metadata.candidate.tokenizer")
        _exact(
            tokenizer_raw,
            name="metadata.candidate.tokenizer",
            required={"kind", "path"},
        )
        tokenizer = GeneratedTokenizer(
            kind=_string(tokenizer_raw, "kind", name="metadata.candidate.tokenizer"),
            path=_string(tokenizer_raw, "path", name="metadata.candidate.tokenizer"),
        )

    features_raw = _object(raw["features"], name="metadata.candidate.features")
    features: dict[str, bool] = {}
    for key, item in features_raw.items():
        if not isinstance(key, str) or not key.strip():
            raise ContractError("metadata.candidate feature names must be non-empty strings")
        if type(item) is not bool:
            raise ContractError(f"metadata.candidate.features.{key} must be boolean")
        features[key] = item

    runtime_raw = _object(raw["runtime_contract"], name="metadata.candidate.runtime_contract")
    _exact(
        runtime_raw,
        name="metadata.candidate.runtime_contract",
        required={"decoder", "input_kind", "io", "decoder_config"},
    )
    io = _object(runtime_raw["io"], name="metadata.candidate.runtime_contract.io")
    decoder_config = _object(
        runtime_raw["decoder_config"],
        name="metadata.candidate.runtime_contract.decoder_config",
    )

    contract = GeneratedCandidateContract(
        schema_version=schema_version,
        candidate_root=_string(raw, "candidate_root", name="metadata.candidate"),
        candidate_id=_string(raw, "candidate_id", name="metadata.candidate"),
        profile_set=_string(raw, "profile_set", name="metadata.candidate"),
        variant=_string(raw, "variant", name="metadata.candidate"),
        profile=_string(raw, "profile", name="metadata.candidate"),
        decoder=_string(raw, "decoder", name="metadata.candidate"),
        artifact_contract=_string(raw, "artifact_contract", name="metadata.candidate"),
        catalog=GeneratedCatalog(
            id=_string(catalog_raw, "id", name="metadata.candidate.catalog"),
            sha256=_string(catalog_raw, "sha256", name="metadata.candidate.catalog"),
        ),
        bundle_sha256=_string(raw, "bundle_sha256", name="metadata.candidate"),
        artifacts=artifacts,
        tokenizer=tokenizer,
        features=features,
        runtime_contract=GeneratedRuntimeContract(
            decoder=_string(
                runtime_raw,
                "decoder",
                name="metadata.candidate.runtime_contract",
            ),
            input_kind=_string(
                runtime_raw,
                "input_kind",
                name="metadata.candidate.runtime_contract",
            ),
            io=dict(io),
            decoder_config=dict(decoder_config),
        ),
    )
    contract.validate()
    return contract
