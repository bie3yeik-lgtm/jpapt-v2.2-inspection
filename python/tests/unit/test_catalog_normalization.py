from __future__ import annotations

from pathlib import Path

from parakeet_onnx.config.allocation_catalog import load_repository_allocation_catalog
from parakeet_onnx.config.catalog import load_repository_catalog


ROOT = Path(__file__).resolve().parents[3]


def test_runtime_catalog_contains_only_runtime_semantics() -> None:
    catalog = load_repository_catalog(ROOT)
    assert catalog.catalog_id == "asr-runtime-catalog-v1"
    profile_set = catalog.profile_set("parakeet-tdt-ctc-v1")
    assert profile_set.profile_id_for("ctc") == "ctc-v1"
    assert profile_set.profile_id_for("tdt") == "tdt-v1"
    assert catalog.decoder_profile("ctc-v1").decoder == "ctc"
    assert catalog.decoder_profile("tdt-v1").decoder == "tdt"


def test_allocation_catalog_is_independent_from_runtime_catalog() -> None:
    allocation = load_repository_allocation_catalog(ROOT)
    runtime = load_repository_catalog(ROOT)
    assert allocation.catalog_id == "hf-allocation-catalog-v1"
    assert allocation.path != runtime.path
    assert allocation.candidate_prefix_key("parakeet-tdt-ctc-v1") == (
        "candidate.parakeet-tdt-ctc-v1"
    )
    assert allocation.prefix("candidate.parakeet-tdt-ctc-v1") == "parakeet-candidate"
    assert allocation.prefix("experiment.cpu_full") == "cpu-full-eval"
    assert allocation.prefix("config.version") == "config"


def test_unknown_profile_set_uses_generic_candidate_prefix() -> None:
    allocation = load_repository_allocation_catalog(ROOT)
    assert allocation.candidate_prefix_key("future-profile-set-v1") == "candidate.default"
    assert allocation.prefix("candidate.default") == "candidate"
