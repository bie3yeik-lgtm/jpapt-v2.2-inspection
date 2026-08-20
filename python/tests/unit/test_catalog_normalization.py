from __future__ import annotations

from pathlib import Path

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
