from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from parakeet_onnx.decoding import VocabularyTokenizer

from .adapter import AsrRuntimeAdapter
from .artifacts import CandidateArtifacts, CandidateMetadataError
from .ctc import CtcRuntimeAdapter
from .inference import OrtCtcRunner
from .model_contract import ModelContract
from .session import OrtSessionConfig, create_session
from .tdt import OrtTdtRuntimeAdapter, TdtRuntimeContract
from .whisper import OrtWhisperRuntimeAdapter, WhisperRuntimeContract

RuntimeFactory = Callable[[CandidateArtifacts, str], AsrRuntimeAdapter]
RuntimeContractValidator = Callable[[CandidateArtifacts], object]
_RUNTIME_FACTORIES: dict[str, RuntimeFactory] = {}
_RUNTIME_CONTRACT_VALIDATORS: dict[str, RuntimeContractValidator] = {}


def register_runtime_factory(
    decoder_id: str,
    factory: RuntimeFactory,
    *,
    contract_validator: RuntimeContractValidator,
) -> None:
    if not decoder_id:
        raise ValueError("decoder_id must not be empty")
    if decoder_id in _RUNTIME_FACTORIES:
        raise ValueError(f"runtime factory already registered: {decoder_id}")
    _RUNTIME_FACTORIES[decoder_id] = factory
    _RUNTIME_CONTRACT_VALIDATORS[decoder_id] = contract_validator


def registered_decoders() -> tuple[str, ...]:
    return tuple(sorted(_RUNTIME_FACTORIES))


def validate_candidate_runtime_contract(candidate: CandidateArtifacts) -> None:
    try:
        validator = _RUNTIME_CONTRACT_VALIDATORS[candidate.decoder]
    except KeyError as exc:
        raise CandidateMetadataError(
            f"no runtime contract validator is registered for decoder "
            f"{candidate.decoder!r}; registered={registered_decoders()}"
        ) from exc
    validator(candidate)


def create_runtime_adapter(
    *,
    candidate: CandidateArtifacts,
    provider_id: str,
) -> AsrRuntimeAdapter:
    validate_candidate_runtime_contract(candidate)
    try:
        factory = _RUNTIME_FACTORIES[candidate.decoder]
    except KeyError as exc:
        raise CandidateMetadataError(
            f"no runtime adapter is registered for decoder {candidate.decoder!r}; registered={registered_decoders()}"
        ) from exc
    return factory(candidate, provider_id)


def _session(candidate: CandidateArtifacts, role: str, provider_id: str) -> Any:
    artifact = candidate.artifact(role)
    return create_session(OrtSessionConfig(model_path=artifact.path, provider_id=provider_id))


def _vocabulary(candidate: CandidateArtifacts) -> VocabularyTokenizer:
    if candidate.tokenizer is not None:
        if candidate.tokenizer.kind != "vocabulary":
            raise CandidateMetadataError(
                f"decoder {candidate.decoder!r} requires tokenizer.kind='vocabulary', got {candidate.tokenizer.kind!r}"
            )
        return VocabularyTokenizer.from_json(candidate.tokenizer.path)

    # schema_version=1 compatibility only. Canonical v2 candidates must declare
    # tokenizer explicitly so metadata remains the source of truth.
    for relative in (
        "vocabulary.json",
        "vocab.json",
        "tokens.json",
        "tokenizer/vocabulary.json",
        "tokenizer/vocab.json",
        "tokenizer/tokens.json",
    ):
        path = candidate.root / relative
        if path.is_file():
            return VocabularyTokenizer.from_json(path)
    raise CandidateMetadataError("candidate metadata does not declare a vocabulary tokenizer")


def _build_ctc(candidate: CandidateArtifacts, provider_id: str) -> AsrRuntimeAdapter:
    artifact = candidate.primary_artifact
    contract = ModelContract.from_candidate(candidate)
    runner = OrtCtcRunner(
        create_session(OrtSessionConfig(model_path=artifact.path, provider_id=provider_id)),
        contract,
    )
    return CtcRuntimeAdapter(runner=runner, tokenizer=_vocabulary(candidate))


def _build_tdt(candidate: CandidateArtifacts, provider_id: str) -> AsrRuntimeAdapter:
    return OrtTdtRuntimeAdapter(
        candidate=candidate,
        encoder_session=_session(candidate, "encoder", provider_id),
        predictor_session=_session(candidate, "predictor", provider_id),
        joint_session=_session(candidate, "joint", provider_id),
        tokenizer=_vocabulary(candidate),
    )


def _load_transformers_processor(path: Path) -> Any:
    try:
        from transformers import AutoProcessor
    except ImportError as exc:
        raise RuntimeError("Whisper runtime requires the project 'transformers-runtime' extra") from exc
    return AutoProcessor.from_pretrained(path, local_files_only=True)


def _build_whisper(candidate: CandidateArtifacts, provider_id: str) -> AsrRuntimeAdapter:
    if candidate.tokenizer is None:
        raise CandidateMetadataError("Whisper candidate metadata must declare tokenizer/processor assets")
    if candidate.tokenizer.kind != "transformers_processor":
        raise CandidateMetadataError("Whisper candidate tokenizer.kind must be 'transformers_processor'")
    processor = _load_transformers_processor(candidate.tokenizer.path)
    with_past = (
        _session(candidate, "decoder_with_past", provider_id) if "decoder_with_past" in candidate.artifacts else None
    )
    return OrtWhisperRuntimeAdapter(
        candidate=candidate,
        encoder_session=_session(candidate, "encoder", provider_id),
        decoder_session=_session(candidate, "decoder", provider_id),
        decoder_with_past_session=with_past,
        processor=processor,
    )


register_runtime_factory("ctc", _build_ctc, contract_validator=ModelContract.from_candidate)
register_runtime_factory("tdt", _build_tdt, contract_validator=TdtRuntimeContract.from_candidate)
register_runtime_factory(
    "whisper_autoregressive",
    _build_whisper,
    contract_validator=WhisperRuntimeContract.from_candidate,
)
