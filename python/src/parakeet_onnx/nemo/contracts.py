from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

MODEL_REPO = "nvidia/parakeet-tdt_ctc-0.6b-ja"
MODEL_FILE = "parakeet-tdt_ctc-0.6b-ja.nemo"
MODEL_LIBRARY = "nemo"
MODEL_LANGUAGE = "ja"
MODEL_LICENSE = "cc-by-4.0"
NORMALIZATION_ID = "asr_metrics_v1"
REFERENCE_SCHEMA_VERSION = 1


class NemoReferenceContractError(ValueError):
    pass


def normalize_text(text: str) -> str:
    """Mirror Rust asr_metrics_v1: Unicode NFKC + whitespace collapse."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fail(message: str) -> NemoReferenceContractError:
    return NemoReferenceContractError(message)


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    observed = set(value)
    if observed != expected:
        missing = sorted(expected - observed)
        unknown = sorted(observed - expected)
        raise _fail(f"{path} fields mismatch: missing={missing}, unknown={unknown}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _fail(f"{path} must be an object")
    return value


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise _fail(f"{path} must be a string")
    if value != value.strip():
        raise _fail(f"{path} must not contain surrounding whitespace")
    if not allow_empty and not value:
        raise _fail(f"{path} must not be empty")
    return value


def _lower_hex(value: Any, path: str, *, minimum: int, maximum: int) -> str:
    text = _string(value, path)
    if not (minimum <= len(text) <= maximum):
        raise _fail(f"{path} has invalid hexadecimal length")
    if any(ch not in "0123456789abcdef" for ch in text):
        raise _fail(f"{path} must be lowercase hexadecimal")
    return text


def _reject_nulls(value: Any, path: str = "$") -> None:
    if value is None:
        raise _fail(f"null is forbidden at {path}")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_nulls(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_nulls(child, f"{path}[{index}]")


@dataclass(frozen=True, slots=True)
class NemoSourceIdentity:
    repo_id: str
    revision_resolved: str
    model_file: str
    model_file_sha256: str
    library: str = MODEL_LIBRARY
    language: str = MODEL_LANGUAGE
    license: str = MODEL_LICENSE

    def validate(self) -> None:
        if self.repo_id != MODEL_REPO:
            raise _fail(f"source.repo_id must be exactly {MODEL_REPO}")
        _lower_hex(
            self.revision_resolved,
            "source.revision_resolved",
            minimum=40,
            maximum=64,
        )
        if self.model_file != MODEL_FILE:
            raise _fail(f"source.model_file must be exactly {MODEL_FILE}")
        _lower_hex(
            self.model_file_sha256,
            "source.model_file_sha256",
            minimum=64,
            maximum=64,
        )
        if self.library != MODEL_LIBRARY:
            raise _fail(f"source.library must be {MODEL_LIBRARY}")
        if self.language != MODEL_LANGUAGE:
            raise _fail(f"source.language must be {MODEL_LANGUAGE}")
        if self.license != MODEL_LICENSE:
            raise _fail(f"source.license must be {MODEL_LICENSE}")

    def to_dict(self) -> dict[str, str]:
        self.validate()
        return {
            "repo_id": self.repo_id,
            "revision_resolved": self.revision_resolved,
            "model_file": self.model_file,
            "model_file_sha256": self.model_file_sha256,
            "library": self.library,
            "language": self.language,
            "license": self.license,
        }


@dataclass(frozen=True, slots=True)
class NemoReferenceSample:
    id: str
    audio_sha256: str
    reference_text: str
    text: str
    normalized_text: str

    def validate(self) -> None:
        _string(self.id, "sample.id")
        _lower_hex(self.audio_sha256, "sample.audio_sha256", minimum=64, maximum=64)
        _string(self.reference_text, "sample.reference_text", allow_empty=True)
        _string(self.text, "sample.text", allow_empty=True)
        _string(self.normalized_text, "sample.normalized_text", allow_empty=True)
        expected = normalize_text(self.text)
        if self.normalized_text != expected:
            raise _fail(
                f"sample {self.id!r} normalized_text does not match {NORMALIZATION_ID}"
            )

    def to_dict(self) -> dict[str, str]:
        self.validate()
        return {
            "id": self.id,
            "audio_sha256": self.audio_sha256,
            "reference_text": self.reference_text,
            "text": self.text,
            "normalized_text": self.normalized_text,
        }


@dataclass(frozen=True, slots=True)
class NemoReferenceDocument:
    reference_run_id: str
    source: NemoSourceIdentity
    samples: tuple[NemoReferenceSample, ...]
    decoder: str = "ctc"
    normalization: str = NORMALIZATION_ID
    schema_version: int = REFERENCE_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != REFERENCE_SCHEMA_VERSION:
            raise _fail("schema_version must be 1")
        _string(self.reference_run_id, "reference_run_id")
        self.source.validate()
        if self.decoder != "ctc":
            raise _fail(
                "Python NeMo reference generation is CTC-only until the Rust TDT runtime exists"
            )
        if self.normalization != NORMALIZATION_ID:
            raise _fail(f"normalization must be {NORMALIZATION_ID}")
        if not self.samples:
            raise _fail("samples must not be empty")
        seen: set[str] = set()
        for sample in self.samples:
            sample.validate()
            if sample.id in seen:
                raise _fail(f"duplicate sample id: {sample.id}")
            seen.add(sample.id)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "reference_run_id": self.reference_run_id,
            "source": self.source.to_dict(),
            "decoder": self.decoder,
            "normalization": self.normalization,
            "samples": [sample.to_dict() for sample in self.samples],
        }

    def write_json(self, path: Path) -> None:
        payload = self.to_dict()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_reference_document(value: Any) -> NemoReferenceDocument:
    _reject_nulls(value)
    root = _mapping(value, "$")
    _exact_keys(
        root,
        {
            "schema_version",
            "reference_run_id",
            "source",
            "decoder",
            "normalization",
            "samples",
        },
        "$",
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise _fail("$.schema_version must be integer 1")

    source_raw = _mapping(root["source"], "$.source")
    _exact_keys(
        source_raw,
        {
            "repo_id",
            "revision_resolved",
            "model_file",
            "model_file_sha256",
            "library",
            "language",
            "license",
        },
        "$.source",
    )
    source = NemoSourceIdentity(
        repo_id=_string(source_raw["repo_id"], "$.source.repo_id"),
        revision_resolved=_lower_hex(
            source_raw["revision_resolved"],
            "$.source.revision_resolved",
            minimum=40,
            maximum=64,
        ),
        model_file=_string(source_raw["model_file"], "$.source.model_file"),
        model_file_sha256=_lower_hex(
            source_raw["model_file_sha256"],
            "$.source.model_file_sha256",
            minimum=64,
            maximum=64,
        ),
        library=_string(source_raw["library"], "$.source.library"),
        language=_string(source_raw["language"], "$.source.language"),
        license=_string(source_raw["license"], "$.source.license"),
    )

    samples_raw = root["samples"]
    if not isinstance(samples_raw, list) or not samples_raw:
        raise _fail("$.samples must be a non-empty array")
    parsed_samples: list[NemoReferenceSample] = []
    for index, item in enumerate(samples_raw):
        path = f"$.samples[{index}]"
        raw = _mapping(item, path)
        _exact_keys(
            raw,
            {"id", "audio_sha256", "reference_text", "text", "normalized_text"},
            path,
        )
        parsed_samples.append(
            NemoReferenceSample(
                id=_string(raw["id"], f"{path}.id"),
                audio_sha256=_lower_hex(
                    raw["audio_sha256"],
                    f"{path}.audio_sha256",
                    minimum=64,
                    maximum=64,
                ),
                reference_text=_string(
                    raw["reference_text"], f"{path}.reference_text", allow_empty=True
                ),
                text=_string(raw["text"], f"{path}.text", allow_empty=True),
                normalized_text=_string(
                    raw["normalized_text"],
                    f"{path}.normalized_text",
                    allow_empty=True,
                ),
            )
        )

    document = NemoReferenceDocument(
        schema_version=1,
        reference_run_id=_string(root["reference_run_id"], "$.reference_run_id"),
        source=source,
        decoder=_string(root["decoder"], "$.decoder"),
        normalization=_string(root["normalization"], "$.normalization"),
        samples=tuple(parsed_samples),
    )
    document.validate()
    return document


def sample_set_digest(samples: Sequence[NemoReferenceSample]) -> str:
    """Stable identity of the exact sample/audio/ground-truth set."""
    digest = hashlib.sha256()
    for sample in samples:
        sample.validate()
        digest.update(sample.id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sample.audio_sha256.encode("ascii"))
        digest.update(b"\0")
        digest.update(sample.reference_text.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
