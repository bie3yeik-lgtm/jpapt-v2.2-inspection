from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class AsrCatalogError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DecoderProfile:
    profile_id: str
    decoder: str
    artifact_contract: str
    tokenizer_kind: str
    required_artifact_roles: tuple[str, ...]
    optional_artifact_roles: tuple[str, ...]
    features: Mapping[str, bool]


@dataclass(frozen=True, slots=True)
class ProfileSet:
    profile_set_id: str
    variants: Mapping[str, str]
    default_variant: str

    def profile_id_for(self, variant: str | None = None) -> str:
        selected = variant or self.default_variant
        try:
            return self.variants[selected]
        except KeyError as exc:
            raise AsrCatalogError(
                f"unknown runtime variant {selected!r} for profile set "
                f"{self.profile_set_id!r}; available={sorted(self.variants)}"
            ) from exc


@dataclass(frozen=True, slots=True)
class AsrCatalog:
    path: Path
    catalog_id: str
    sha256: str
    decoder_profiles: Mapping[str, DecoderProfile]
    profile_sets: Mapping[str, ProfileSet]

    @classmethod
    def load(cls, path: str | Path) -> "AsrCatalog":
        resolved = Path(path).expanduser().resolve()
        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AsrCatalogError(f"failed to load ASR catalog {resolved}: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise AsrCatalogError("ASR catalog must be a schema_version=1 object")

        catalog_id = _string(raw, "catalog_id")
        profiles_raw = _mapping(raw, "decoder_profiles")
        decoder_profiles: dict[str, DecoderProfile] = {}
        for profile_id, value in profiles_raw.items():
            profile_id = _nonempty_key(profile_id, "decoder_profiles")
            if not isinstance(value, Mapping):
                raise AsrCatalogError(
                    f"decoder_profiles.{profile_id} must be an object"
                )
            features_raw = _mapping(value, "features")
            features: dict[str, bool] = {}
            for key, feature_value in features_raw.items():
                if not isinstance(key, str) or not isinstance(feature_value, bool):
                    raise AsrCatalogError(
                        f"decoder_profiles.{profile_id}.features must contain booleans"
                    )
                features[key] = feature_value
            decoder_profiles[profile_id] = DecoderProfile(
                profile_id=profile_id,
                decoder=_string(value, "decoder"),
                artifact_contract=_string(value, "artifact_contract"),
                tokenizer_kind=_string(value, "tokenizer_kind"),
                required_artifact_roles=_string_array(
                    value, "required_artifact_roles"
                ),
                optional_artifact_roles=_string_array(
                    value, "optional_artifact_roles", required=False
                ),
                features=features,
            )

        sets_raw = _mapping(raw, "profile_sets")
        profile_sets: dict[str, ProfileSet] = {}
        for profile_set_id, value in sets_raw.items():
            profile_set_id = _nonempty_key(profile_set_id, "profile_sets")
            if not isinstance(value, Mapping):
                raise AsrCatalogError(
                    f"profile_sets.{profile_set_id} must be an object"
                )
            variants_raw = _mapping(value, "variants")
            variants: dict[str, str] = {}
            for variant, profile_id in variants_raw.items():
                variant = _nonempty_key(
                    variant, f"profile_sets.{profile_set_id}.variants"
                )
                profile_id = _string_value(
                    profile_id,
                    f"profile_sets.{profile_set_id}.variants.{variant}",
                )
                if profile_id not in decoder_profiles:
                    raise AsrCatalogError(
                        f"profile set {profile_set_id!r} references unknown decoder "
                        f"profile {profile_id!r}"
                    )
                variants[variant] = profile_id
            default_variant = _string(value, "default_variant")
            if default_variant not in variants:
                raise AsrCatalogError(
                    f"profile_sets.{profile_set_id}.default_variant must be one of "
                    f"{sorted(variants)}"
                )
            profile_sets[profile_set_id] = ProfileSet(
                profile_set_id=profile_set_id,
                variants=variants,
                default_variant=default_variant,
            )

        canonical = json.dumps(
            raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return cls(
            path=resolved,
            catalog_id=catalog_id,
            sha256=hashlib.sha256(canonical).hexdigest(),
            decoder_profiles=decoder_profiles,
            profile_sets=profile_sets,
        )

    def profile_set(self, profile_set_id: str) -> ProfileSet:
        try:
            return self.profile_sets[profile_set_id]
        except KeyError as exc:
            raise AsrCatalogError(
                f"unknown profile set {profile_set_id!r}; "
                f"available={sorted(self.profile_sets)}"
            ) from exc

    def decoder_profile(self, profile_id: str) -> DecoderProfile:
        try:
            return self.decoder_profiles[profile_id]
        except KeyError as exc:
            raise AsrCatalogError(
                f"unknown decoder profile {profile_id!r}; "
                f"available={sorted(self.decoder_profiles)}"
            ) from exc


def load_repository_catalog(repository_root: str | Path) -> AsrCatalog:
    return AsrCatalog.load(Path(repository_root) / "config" / "asr-catalog.json")


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise AsrCatalogError(f"{key} must be an object")
    return item


def _string(value: Mapping[str, Any], key: str) -> str:
    return _string_value(value.get(key), key)


def _string_value(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AsrCatalogError(f"{name} must be a non-empty string")
    return value.strip()


def _string_array(
    value: Mapping[str, Any], key: str, *, required: bool = True
) -> tuple[str, ...]:
    item = value.get(key)
    if item is None and not required:
        return ()
    if not isinstance(item, list) or not all(
        isinstance(entry, str) and entry.strip() for entry in item
    ):
        raise AsrCatalogError(f"{key} must be a string array")
    return tuple(entry.strip() for entry in item)


def _nonempty_key(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AsrCatalogError(f"{name} keys must be non-empty strings")
    return value.strip()
