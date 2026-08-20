from __future__ import annotations

from copy import deepcopy

import pytest

from parakeet_onnx.contract_io import parse_run_context
from parakeet_onnx.contracts import ContractError
from parakeet_onnx.generated_candidate_io import parse_generated_candidate_contract

SHA = "a" * 64


def _candidate() -> dict[str, object]:
    return {
        "schema_version": 1,
        "candidate_root": "/candidate",
        "candidate_id": "candidate-000001",
        "profile_set": "parakeet-tdt-ctc-v1",
        "variant": "ctc",
        "profile": "ctc-v1",
        "decoder": "ctc",
        "artifact_contract": "ctc-single-graph-v1",
        "catalog": {"id": "asr-runtime-catalog-v1", "sha256": SHA},
        "bundle_sha256": SHA,
        "artifacts": {"primary": {"path": "model.onnx", "sha256": SHA, "size_bytes": 1}},
        "features": {},
        "runtime_contract": {
            "decoder": "ctc",
            "input_kind": "canonical_waveform",
            "io": {
                "primary": {
                    "input": "audio_signal",
                    "length_input": "length",
                    "logits_output": "logits",
                }
            },
            "decoder_config": {"blank_id": 0},
        },
    }


def _run_context() -> dict[str, object]:
    candidate = _candidate()
    return {
        "schema_version": 2,
        "run_id": "run-1",
        "created_at": "2026-08-16T00:00:00+00:00",
        "config_identity": "model:linux:cpu:smoke",
        "model_id": "model",
        "environment_id": "linux",
        "provider_id": "cpu",
        "evaluation_id": "smoke",
        "artifact": {
            "path": "candidate/model.onnx",
            "sha256": SHA,
            "size_bytes": 1,
            "candidate_id": "candidate-000001",
            "artifact_role": "primary",
        },
        "git": {
            "repository": "owner/repo",
            "commit": "deadbeef",
            "ref": "refs/heads/main",
            "dirty": False,
        },
        "host": {
            "os": "Linux",
            "architecture": "x86_64",
            "hostname": "runner",
            "python_version": "3.12.0",
            "implementation": "CPython",
            "is_wsl": False,
            "github_runner_os": "Linux",
            "github_runner_arch": "X64",
            "github_run_id": "1",
            "github_run_attempt": "1",
        },
        "runtime": {
            "implementation": "python",
            "backend": "onnxruntime",
            "backend_version": "1.28.0",
            "provider_id": "cpu",
            "provider_ort_name": "CPUExecutionProvider",
            "provider_available": True,
        },
        "revisions": {
            "config_version": "config-000001",
            "bundle_sha256": SHA,
            "runtime": {
                "document_sha256": SHA,
                "catalog": {"id": "asr-runtime-catalog-v1", "sha256": SHA},
                "profile_set": "parakeet-tdt-ctc-v1",
            },
            "reference": {
                "document_sha256": SHA,
                "development_artifact": {"repo_id": "dev/model", "revision": "dev"},
                "upstream": {"repo_id": "up/model", "revision": "up"},
                "tokenizer": {"repo_id": "up/model", "revision": "tok"},
                "reference_id": "reference-v1",
                "reference_revision": "ref",
                "canonical_framework": "nemo",
            },
            "evaluation_schema": {
                "document_sha256": SHA,
                "schema_id": "eval-v1",
                "schema_revision": "eval",
            },
            "datasets": {"document_sha256": SHA, "entries": []},
        },
        "config": {
            "identity": "model:linux:cpu:smoke",
            "sources": {
                "model": "config/models/model.toml",
                "provider": "config/providers/cpu.toml",
                "environment": "config/environments/linux.toml",
                "evaluation": "config/evaluation/smoke.toml",
            },
            "resolved": {
                "model": {},
                "provider": {},
                "environment": {},
                "evaluation": {},
                "resolved": {
                    "model_id": "model",
                    "provider_id": "cpu",
                    "environment_id": "linux",
                    "evaluation_id": "smoke",
                },
            },
        },
        "metadata": {
            "candidate": candidate,
            "runtime_variant": "ctc",
            "runtime_profile": "ctc-v1",
        },
    }


def test_strict_run_context_parser_accepts_canonical_shape() -> None:
    context = parse_run_context(_run_context())
    parse_generated_candidate_contract(context.metadata["candidate"])
    assert context.artifact.candidate_id == "candidate-000001"


def test_run_context_rejects_candidate_profile_set_mismatch() -> None:
    value = _run_context()
    candidate = value["metadata"]["candidate"]  # type: ignore[index]
    candidate["profile_set"] = "whisper-autoregressive-v1"  # type: ignore[index]
    with pytest.raises(ContractError, match="profile_set"):
        parse_run_context(value)


def test_generated_candidate_parser_rejects_unknown_fields() -> None:
    value = _candidate()
    value["guessed_runtime"] = True
    with pytest.raises(ContractError, match="unknown fields"):
        parse_generated_candidate_contract(value)


def test_run_context_rejects_null_before_type_parsing() -> None:
    value = deepcopy(_run_context())
    value["runtime"]["provider_available"] = None  # type: ignore[index]
    with pytest.raises(ContractError, match="must not contain null"):
        parse_run_context(value)
