from __future__ import annotations

from pathlib import Path

from parakeet_onnx.datasets.cache import DatasetCache
from parakeet_onnx.datasets.models import (
    ResolvedDatasetSample,
    ResolvedManifest,
)


def _resolved_manifest() -> ResolvedManifest:
    sample = ResolvedDatasetSample(
        id="dataset-entry-abc",
        manifest_entry_id="entry",
        dataset_id="dataset",
        dataset_repo_id="org/dataset",
        dataset_revision="rev-a",
        subset=None,
        split="test",
        row_index=1,
        source_identity="id:1",
        selection_hash="a" * 64,
        selection_rank=1,
        duration_sec=1.0,
        sample_rate_hz=16_000,
        transcription="テスト",
        tags=("smoke",),
        audio_path="/tmp/audio.wav",
        audio_sha256="b" * 64,
    )

    return ResolvedManifest(
        schema_version=1,
        manifest_path="evaluation/manifests/smoke.jsonl",
        expected_sample_count=1,
        resolved_sample_count=1,
        samples=(sample,),
    )


def test_cache_key_changes_with_lock_hash() -> None:
    manifest = b"hello"

    a = DatasetCache.make_key(
        manifest_bytes=manifest,
        datasets_lock_sha256="a" * 64,
    )
    b = DatasetCache.make_key(
        manifest_bytes=manifest,
        datasets_lock_sha256="b" * 64,
    )

    assert a != b


def test_cache_roundtrip(tmp_path: Path) -> None:
    cache = DatasetCache(
        tmp_path / "cache"
    )

    resolved = _resolved_manifest()

    key = cache.make_key(
        manifest_bytes=b"manifest",
        datasets_lock_sha256="a" * 64,
    )

    assert cache.load(key) is None

    cache.store(
        key,
        resolved,
    )

    loaded = cache.load(key)

    assert loaded is not None
    assert loaded.samples[0].id == resolved.samples[0].id
    assert loaded.samples[0].audio_sha256 == "b" * 64
