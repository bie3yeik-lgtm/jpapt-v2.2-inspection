from __future__ import annotations

import hashlib

import pytest

from parakeet_onnx.nemo import (
    MODEL_FILE,
    MODEL_REPO,
    NemoReferenceContractError,
    NemoReferenceDocument,
    NemoReferenceSample,
    NemoSourceIdentity,
    normalize_text,
    parse_reference_document,
    sample_set_digest,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _document() -> NemoReferenceDocument:
    sample = NemoReferenceSample(
        id="sample-0001",
        audio_sha256=_sha("audio"),
        reference_text="今日は テストです",
        text="今日は   テストです",
        normalized_text="今日は テストです",
    )
    return NemoReferenceDocument(
        reference_run_id="nemo-0123456789ab-ctc-abcdef012345",
        source=NemoSourceIdentity(
            repo_id=MODEL_REPO,
            revision_resolved="0" * 40,
            model_file=MODEL_FILE,
            model_file_sha256="1" * 64,
        ),
        samples=(sample,),
    )


def test_reference_roundtrip_is_strict() -> None:
    value = _document().to_dict()
    parsed = parse_reference_document(value)
    assert parsed == _document()


def test_reference_rejects_unknown_fields() -> None:
    value = _document().to_dict()
    value["guessed_metric"] = 0.1
    with pytest.raises(NemoReferenceContractError, match="unknown"):
        parse_reference_document(value)


def test_reference_rejects_null_recursively() -> None:
    value = _document().to_dict()
    value["samples"][0]["text"] = None
    with pytest.raises(NemoReferenceContractError, match="null is forbidden"):
        parse_reference_document(value)


def test_reference_recomputes_normalization() -> None:
    value = _document().to_dict()
    value["samples"][0]["normalized_text"] = "producer supplied value"
    with pytest.raises(NemoReferenceContractError, match="normalized_text"):
        parse_reference_document(value)


def test_normalization_matches_asr_metrics_v1_contract() -> None:
    assert normalize_text("ＡＢＣ\t  日本語\n") == "ABC 日本語"


def test_sample_set_digest_is_order_sensitive_and_deterministic() -> None:
    first = _document().samples[0]
    second = NemoReferenceSample(
        id="sample-0002",
        audio_sha256=_sha("audio-2"),
        reference_text="別の正解",
        text="別の正解",
        normalized_text="別の正解",
    )
    assert sample_set_digest((first, second)) == sample_set_digest((first, second))
    assert sample_set_digest((first, second)) != sample_set_digest((second, first))
