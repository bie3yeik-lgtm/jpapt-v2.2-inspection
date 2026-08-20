from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import time
from pathlib import Path

import jiwer


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="benchmark-runner")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--model-id", required=True)
    p.add_argument("--model-revision", required=True)
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--dataset-revision", required=True)
    p.add_argument("--decoder", choices=("tdt", "ctc", "whisper"), required=True)
    p.add_argument("--batch-size", type=int, choices=(1, 2, 4), required=True)
    p.add_argument("--precision", choices=("float32", "float16", "bfloat16"), required=True)
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--provider", choices=("cuda", "cpu"), default="cuda")
    p.add_argument("--service-id", choices=("hf-jobs", "hf-inference-endpoint", "runpod-pod"), required=True)
    p.add_argument("--gpu", required=True)
    p.add_argument("--profile", choices=("lough", "precise"), required=True)
    p.add_argument("--fixture-repo-id", required=True)
    p.add_argument("--fixture-revision", required=True)
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


def release_inference_temporaries(torch_module: object, device: object) -> None:
    """Release transient inference objects without unloading the model.

    The model must remain resident for the benchmark, but NeMo may retain
    references to tensors created by a warm-up or a previous measurement.
    Cleanup is deliberately outside the timed section so it cannot affect RTF.
    """
    gc.collect()
    if getattr(device, "type", None) == "cuda":
        torch_module.cuda.empty_cache()
        torch_module.cuda.ipc_collect()


def main() -> int:
    args = parser().parse_args()
    if args.repeat < 1:
        raise SystemExit("--repeat must be positive")
    samples, local_manifest_sha256 = load_manifest(args.manifest)
    manifest_sha256 = os.environ.get("RTF_FIXTURE_MANIFEST_SHA256", local_manifest_sha256)
    try:
        import torch
        from huggingface_hub import snapshot_download
        from nemo.collections.asr.models import ASRModel

        if args.provider == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA provider requested but torch.cuda.is_available() is false")
        device = torch.device("cuda" if args.provider == "cuda" else "cpu")
        if args.precision == "float16":
            autocast = torch.float16
        elif args.precision == "bfloat16":
            autocast = torch.bfloat16
        else:
            autocast = None

        model_dir = Path(snapshot_download(
            repo_id=args.model_id,
            revision=args.model_revision,
            token=os.environ.get("HF_TOKEN"),
            allow_patterns=["*.nemo", "*.json", "*.yaml"],
        ))
        nemo_files = sorted(model_dir.glob("*.nemo"))
        if not nemo_files:
            raise RuntimeError(f"no .nemo model was found in pinned snapshot: {model_dir}")
        model = ASRModel.restore_from(
            restore_path=str(nemo_files[0]),
            map_location=device,
        )
        model = model.to(device).eval()
        paths = [str(sample["audio_path"]) for sample in samples]
        references = [str(sample.get("text", "")) for sample in samples]
        durations = [float(sample["audio_duration_sec"]) for sample in samples]
        with torch.inference_mode():
            with torch.autocast(device_type=device.type, dtype=autocast, enabled=autocast is not None):
                warmup_hypotheses = model.transcribe(
                    paths[:1],
                    batch_size=1,
                )
            del warmup_hypotheses
            release_inference_temporaries(torch, device)
            if device.type == "cuda":
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
            timings = []
            hypotheses = []
            with torch.autocast(device_type=device.type, dtype=autocast, enabled=autocast is not None):
                for _ in range(args.repeat):
                    release_inference_temporaries(torch, device)
                    started = time.perf_counter()
                    hypotheses = model.transcribe(paths, batch_size=args.batch_size)
                    if device.type == "cuda":
                        torch.cuda.synchronize()
                    timings.append(time.perf_counter() - started)
                    if _ + 1 < args.repeat:
                        release_inference_temporaries(torch, device)
            elapsed = sum(timings) / len(timings)
        texts = [str(item.text if hasattr(item, "text") else item) for item in hypotheses]
        reference_text = " ".join(references).strip()
        hypothesis_text = " ".join(texts).strip()
        audio_duration = sum(durations)
        processing_duration = max(elapsed, 1e-9)
        result = {
            "schema_version": 1,
            "run_id": args.run_id,
            "status": "completed",
            "model_id": args.model_id,
            "model_revision": args.model_revision,
            "dataset_id": args.dataset_id,
            "dataset_revision": args.dataset_revision,
            "decoder": args.decoder,
            "batch_size": args.batch_size,
            "precision": args.precision,
            "repeat": args.repeat,
            "provider": args.provider,
            "environment": "linux",
            "service_id": args.service_id,
            "gpu": args.gpu,
            "dtype": args.precision,
            "image_digest": os.environ.get("RTF_IMAGE_DIGEST", ""),
            "inspection_profile": args.profile,
            "fixture_repo_id": args.fixture_repo_id,
            "fixture_revision": args.fixture_revision,
            "manifest_sha256": manifest_sha256,
            "audio_duration_sec": audio_duration,
            "processing_duration_sec": processing_duration,
            "rtf": processing_duration / audio_duration,
            "rtfx": audio_duration / processing_duration,
            "rtf_scope": "model",
            "cer": jiwer.cer(reference_text, hypothesis_text) if reference_text else None,
            "peak_vram_bytes": torch.cuda.max_memory_allocated() if device.type == "cuda" else None,
            "gpu_utilization_pct": None,
            "gpu_price_per_hour": None,
            "cost_per_audio_hour": None,
        }
    except Exception as exc:
        result = {
            "schema_version": 1,
            "run_id": args.run_id,
            "status": "blocked",
            "error_code": "BENCHMARK_INFERENCE_FAILED",
            "error_message": str(exc),
            "model_id": args.model_id,
            "model_revision": args.model_revision,
            "dataset_id": args.dataset_id,
            "dataset_revision": args.dataset_revision,
            "decoder": args.decoder,
            "batch_size": args.batch_size,
            "precision": args.precision,
            "repeat": args.repeat,
            "provider": args.provider,
            "environment": "linux",
            "service_id": args.service_id,
            "gpu": args.gpu,
            "dtype": args.precision,
            "image_digest": os.environ.get("RTF_IMAGE_DIGEST", ""),
            "inspection_profile": args.profile,
            "fixture_repo_id": args.fixture_repo_id,
            "fixture_revision": args.fixture_revision,
            "sample_count": len(samples),
            "manifest_sha256": manifest_sha256,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0
