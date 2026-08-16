from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .contracts import (
    MODEL_FILE,
    MODEL_REPO,
    NemoReferenceDocument,
    NemoReferenceSample,
    NemoSourceIdentity,
    normalize_text,
    sample_set_digest,
    sha256_file,
)


class NemoReferenceGenerationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedInputSample:
    id: str
    audio_path: Path
    audio_sha256: str
    transcription: str


def _require_string(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise NemoReferenceGenerationError(f"{name} must be a string")
    if value != value.strip():
        raise NemoReferenceGenerationError(f"{name} has surrounding whitespace")
    if not allow_empty and not value:
        raise NemoReferenceGenerationError(f"{name} must not be empty")
    return value


def load_resolved_inputs(path: Path) -> tuple[ResolvedInputSample, ...]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NemoReferenceGenerationError(
            f"failed to load resolved manifest {path}: {exc}"
        ) from exc

    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise NemoReferenceGenerationError("resolved manifest schema_version must be 1")
    samples = value.get("samples")
    if not isinstance(samples, list) or not samples:
        raise NemoReferenceGenerationError("resolved manifest samples must be non-empty")
    expected = value.get("expected_sample_count")
    resolved = value.get("resolved_sample_count")
    if type(expected) is not int or type(resolved) is not int:
        raise NemoReferenceGenerationError("manifest sample counts must be integers")
    if expected != len(samples) or resolved != len(samples):
        raise NemoReferenceGenerationError("resolved/expected sample counts disagree")

    observed_ids: set[str] = set()
    result: list[ResolvedInputSample] = []
    for index, raw in enumerate(samples):
        if not isinstance(raw, dict):
            raise NemoReferenceGenerationError(f"samples[{index}] must be an object")
        sample_id = _require_string(raw.get("id"), f"samples[{index}].id")
        if sample_id in observed_ids:
            raise NemoReferenceGenerationError(f"duplicate sample id: {sample_id}")
        observed_ids.add(sample_id)

        audio_path = Path(
            _require_string(raw.get("audio_path"), f"samples[{index}].audio_path")
        )
        audio_sha = _require_string(
            raw.get("audio_sha256"), f"samples[{index}].audio_sha256"
        )
        if len(audio_sha) != 64 or any(ch not in "0123456789abcdef" for ch in audio_sha):
            raise NemoReferenceGenerationError(
                f"samples[{index}].audio_sha256 must be lowercase SHA256"
            )
        transcription = _require_string(
            raw.get("transcription"),
            f"samples[{index}].transcription",
            allow_empty=True,
        )
        if not audio_path.is_file():
            raise NemoReferenceGenerationError(
                f"materialized audio file is missing: {audio_path}"
            )
        observed_sha = sha256_file(audio_path)
        if observed_sha != audio_sha:
            raise NemoReferenceGenerationError(
                f"audio SHA mismatch before NeMo inference: {sample_id}"
            )
        result.append(
            ResolvedInputSample(
                id=sample_id,
                audio_path=audio_path,
                audio_sha256=audio_sha,
                transcription=transcription,
            )
        )
    return tuple(result)


def transcribed_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    text = getattr(value, "text", None)
    if isinstance(text, str):
        return text
    if isinstance(value, (tuple, list)) and len(value) == 1:
        return transcribed_text(value[0])
    raise NemoReferenceGenerationError(
        f"unsupported NeMo transcription result type: {type(value)!r}"
    )


def resolve_model_revision(model_repo: str, requested_revision: str) -> str:
    if model_repo != MODEL_REPO:
        raise NemoReferenceGenerationError(f"model_repo must be exactly {MODEL_REPO}")
    requested_revision = _require_string(requested_revision, "model_revision")
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise NemoReferenceGenerationError(
            "huggingface_hub is required; install the project with the hf extra"
        ) from exc
    info = HfApi().model_info(model_repo, revision=requested_revision)
    revision = info.sha
    if not isinstance(revision, str):
        raise NemoReferenceGenerationError("Hugging Face did not return a model SHA")
    revision = revision.lower()
    if len(revision) < 40 or any(ch not in "0123456789abcdef" for ch in revision):
        raise NemoReferenceGenerationError("resolved model revision is not immutable hex")
    return revision


def download_model(model_repo: str, revision: str) -> Path:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise NemoReferenceGenerationError(
            "huggingface_hub is required; install the project with the hf extra"
        ) from exc
    path = hf_hub_download(
        repo_id=model_repo,
        filename=MODEL_FILE,
        revision=revision,
    )
    model_path = Path(path)
    if not model_path.is_file():
        raise NemoReferenceGenerationError(f"downloaded model is missing: {model_path}")
    return model_path


def _load_nemo_ctc(model_path: Path) -> tuple[Any, Any]:
    try:
        import torch
        from nemo.collections.asr.models import ASRModel
    except ImportError as exc:
        raise NemoReferenceGenerationError(
            "NeMo reference generation must run inside a NeMo/PyTorch environment"
        ) from exc

    model = ASRModel.restore_from(restore_path=str(model_path), map_location="cpu")
    model.eval()
    model.change_decoding_strategy(decoder_type="ctc")
    return model, torch


def build_reference_document(
    *,
    model_repo: str,
    model_revision: str,
    resolved_manifest: Path,
    batch_size: int = 1,
) -> NemoReferenceDocument:
    if batch_size <= 0:
        raise NemoReferenceGenerationError("batch_size must be positive")

    samples = load_resolved_inputs(resolved_manifest)
    revision = resolve_model_revision(model_repo, model_revision)
    model_path = download_model(model_repo, revision)
    model_sha = sha256_file(model_path)

    model, torch = _load_nemo_ctc(model_path)
    audio_paths = [str(sample.audio_path) for sample in samples]
    with torch.inference_mode():
        outputs = model.transcribe(audio=audio_paths, batch_size=batch_size)
    if not isinstance(outputs, Sequence) or len(outputs) != len(samples):
        raise NemoReferenceGenerationError("NeMo transcribe output count mismatch")

    evidence_samples: list[NemoReferenceSample] = []
    for sample, output in zip(samples, outputs, strict=True):
        text = transcribed_text(output)
        evidence_samples.append(
            NemoReferenceSample(
                id=sample.id,
                audio_sha256=sample.audio_sha256,
                reference_text=sample.transcription,
                text=text,
                normalized_text=normalize_text(text),
            )
        )

    digest = sample_set_digest(evidence_samples)
    document = NemoReferenceDocument(
        reference_run_id=f"nemo-{revision[:12]}-ctc-{digest[:12]}",
        source=NemoSourceIdentity(
            repo_id=model_repo,
            revision_resolved=revision,
            model_file=MODEL_FILE,
            model_file_sha256=model_sha,
        ),
        samples=tuple(evidence_samples),
    )
    document.validate()
    return document
