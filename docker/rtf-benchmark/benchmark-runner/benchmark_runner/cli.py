from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="benchmark-runner")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--model-id", required=True)
    p.add_argument("--model-revision", required=True)
    p.add_argument("--decoder", choices=("tdt", "ctc", "whisper"), required=True)
    p.add_argument("--batch-size", type=int, choices=(1, 8, 32), required=True)
    p.add_argument("--precision", choices=("float32", "float16", "bfloat16"), required=True)
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--provider", choices=("cuda", "cpu"), default="cuda")
    p.add_argument("--service-id", choices=("hf-inference-endpoint", "runpod-pod"), required=True)
    p.add_argument("--gpu", required=True)
    return p


def load_manifest(path: Path) -> tuple[list[dict[str, object]], str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    samples = [json.loads(line) for line in lines]
    if not samples:
        raise ValueError("manifest contains no samples")
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, dict):
            raise ValueError(f"manifest line {index} is not an object")
        duration = sample.get("audio_duration_sec")
        audio_path = sample.get("audio_path")
        if not isinstance(audio_path, str) or not Path(audio_path).is_file():
            raise ValueError(f"manifest line {index} audio_path is not a materialized local file")
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"manifest line {index} audio_duration_sec must be finite and positive")
    return samples, hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parser().parse_args()
    if args.repeat < 1:
        raise SystemExit("--repeat must be positive")
    samples, manifest_sha256 = load_manifest(args.manifest)
    # Model-specific inference remains a separate unit. Contract validation
    # must never be presented as a completed benchmark.
    result = {
        "schema_version": 1,
        "run_id": args.run_id,
        "status": "blocked",
        "error_code": "BENCHMARK_INFERENCE_NOT_IMPLEMENTED",
        "error_message": "manifest contract validated; provider runner is not connected",
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "decoder": args.decoder,
        "batch_size": args.batch_size,
        "precision": args.precision,
        "repeat": args.repeat,
        "provider": args.provider,
        "service_id": args.service_id,
        "gpu": args.gpu,
        "sample_count": len(samples),
        "manifest_sha256": manifest_sha256,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0
