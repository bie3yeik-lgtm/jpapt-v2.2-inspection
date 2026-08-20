#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from parakeet_onnx.config import resolve_config
from parakeet_onnx.datasets import (
    DatasetMaterializer,
    DatasetResolver,
    HuggingFaceDatasetBackend,
)
from parakeet_onnx.hf.revisions import load_revision_bundle


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Materialize the locked evaluation manifest for the Rust evaluator.")
    p.add_argument("--provider", required=True)
    p.add_argument("--evaluation", required=True)
    p.add_argument("--environment", required=True)
    p.add_argument("--model-config", default="parakeet-tdt_ctc-0.6b-ja")
    p.add_argument("--revisions", type=Path, default=Path(".ci/hf/config/revisions"))
    p.add_argument("--output", type=Path, required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    config = resolve_config(
        model=args.model_config,
        provider=args.provider,
        evaluation=args.evaluation,
        environment=args.environment,
    )
    revisions = load_revision_bundle(args.revisions)
    materializer_root = Path(str(config.environment.get("path.materialized_audio_cache", ".cache/evaluation/audio")))
    if not materializer_root.is_absolute():
        materializer_root = config.repository_root / materializer_root
    hf_cache = Path(str(config.environment.get("path.huggingface_cache", ".cache/huggingface")))
    if not hf_cache.is_absolute():
        hf_cache = config.repository_root / hf_cache
    resolver = DatasetResolver(
        dataset_lock=revisions.datasets,
        backend=HuggingFaceDatasetBackend(cache_dir=hf_cache, streaming=False),
        materializer=DatasetMaterializer(materializer_root),
        repository_root=config.repository_root,
    )
    resolved = resolver.resolve(
        config.manifest_path,
        expected_sample_count=config.evaluation.expected_sample_count,
    )
    resolved.write_json(args.output)
    print(f"resolved_manifest={args.output}")
    print(f"samples={resolved.resolved_sample_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
