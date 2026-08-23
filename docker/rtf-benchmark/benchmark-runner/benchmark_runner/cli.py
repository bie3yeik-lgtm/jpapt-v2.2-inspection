from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import jiwer

from benchmark_runner.transcribe_compat import transcribe


class ProviderMetricsError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def read_nonnegative_float_env(name: str) -> float | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ProviderMetricsError("PROVIDER_METRICS_INVALID", f"{name} must be numeric") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ProviderMetricsError("PROVIDER_METRICS_INVALID", f"{name} must be finite and non-negative")
    return parsed


class GpuUtilizationSampler:
    """Sample NVIDIA utilization only while the timed inference is running."""

    def __init__(self, interval_seconds: float = 0.5) -> None:
        self.executable = shutil.which("nvidia-smi")
        self.interval_seconds = interval_seconds
        self.samples: list[float] = []
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def _sample(self) -> None:
        if self.executable is None:
            return
        while not self.stop_event.is_set():
            try:
                completed = subprocess.run(
                    [
                        self.executable,
                        "--query-gpu=utilization.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                values = [float(line.strip()) for line in completed.stdout.splitlines() if line.strip()]
                if values and all(math.isfinite(value) and 0 <= value <= 100 for value in values):
                    self.samples.append(sum(values) / len(values))
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
            self.stop_event.wait(self.interval_seconds)

    def __enter__(self) -> GpuUtilizationSampler:
        if self.executable is not None:
            self.thread = threading.Thread(target=self._sample, name="rtf-gpu-utilization", daemon=True)
            self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3)

    @property
    def average(self) -> float | None:
        return sum(self.samples) / len(self.samples) if self.samples else None


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
    p.add_argument("--batch-size", type=int, choices=(1, 8, 32), required=True)
    p.add_argument("--precision", choices=("float32", "float16", "bfloat16"), required=True)
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--provider", choices=("cuda", "cpu"), default="cuda")
    p.add_argument("--service-id", choices=("hf-jobs", "hf-inference-endpoint", "runpod-pod"), required=True)
    p.add_argument("--gpu", required=True)
    p.add_argument("--profile", choices=("smoke", "pref", "probe"), required=True)
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


def load_model(asr_model: object, snapshot_download: object, torch_module: object,
               *, model_id: str, model_revision: str, device: object,
               token: str | None) -> object:
    """Restore one isolated NeMo model instance for one timed repeat.

    NeMo's temporary transcription state is not guaranteed to be reusable
    after a CUDA inference. Reusing the same instance for warmup, measurement,
    and repeat runs caused T4 illegal-memory-access failures. The snapshot is
    cached, so restoring a fresh instance is safer than retrying a poisoned
    CUDA context or paying for another provider job.
    """

    model_dir = Path(snapshot_download(
        repo_id=model_id,
        revision=model_revision,
        token=token,
        allow_patterns=["*.nemo", "*.json", "*.yaml"],
    ))
    nemo_files = sorted(model_dir.glob("*.nemo"))
    if not nemo_files:
        raise RuntimeError(f"no .nemo model was found in pinned snapshot: {model_dir}")
    return asr_model.restore_from(
        restore_path=str(nemo_files[0]),
        map_location=device,
    ).to(device).eval()


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
        # The content probe intentionally runs without autocast. Keep the
        # benchmark on the same conservative provider path unless an explicit
        # diagnostic/compatibility experiment opts in.
        autocast = None
        if os.environ.get("RTF_ENABLE_AUTOCAST", "0").lower() in {"1", "true"}:
            if args.precision == "float16":
                autocast = torch.float16
            elif args.precision == "bfloat16":
                autocast = torch.bfloat16
        paths = [str(sample["audio_path"]) for sample in samples]
        references = [str(sample.get("text", "")) for sample in samples]
        durations = [float(sample["audio_duration_sec"]) for sample in samples]
        gpu_price_per_hour = read_nonnegative_float_env("RTF_GPU_PRICE_PER_HOUR")
        utilization_samples: list[float] = []
        with torch.inference_mode():
            if device.type == "cuda":
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
            timings = []
            hypotheses = []
            for _ in range(args.repeat):
                model = load_model(
                    ASRModel,
                    snapshot_download,
                    torch,
                    model_id=args.model_id,
                    model_revision=args.model_revision,
                    device=device,
                    token=os.environ.get("HF_TOKEN"),
                )
                with torch.autocast(device_type=device.type, dtype=autocast, enabled=autocast is not None):
                    release_inference_temporaries(torch, device)
                    with GpuUtilizationSampler() as utilization_sampler:
                        started = time.perf_counter()
                        hypotheses = transcribe(
                            model,
                            paths,
                            batch_size=args.batch_size,
                            torch_module=torch,
                            device=device,
                        )
                        processing_time = time.perf_counter() - started
                    timings.append(processing_time)
                    if utilization_sampler.average is not None:
                        utilization_samples.append(utilization_sampler.average)
                del model
                release_inference_temporaries(torch, device)
            elapsed = sum(timings) / len(timings)
        texts = [str(item.text if hasattr(item, "text") else item) for item in hypotheses]
        del hypotheses
        release_inference_temporaries(torch, device)
        reference_text = " ".join(references).strip()
        hypothesis_text = " ".join(texts).strip()
        audio_duration = sum(durations)
        processing_duration = max(elapsed, 1e-9)
        gpu_utilization_pct = (
            sum(utilization_samples) / len(utilization_samples)
            if utilization_samples
            else None
        )
        if args.service_id == "runpod-pod" and gpu_price_per_hour is None:
            raise ProviderMetricsError(
                "RUNPOD_GPU_PRICE_UNAVAILABLE",
                "RunPod did not provide RTF_GPU_PRICE_PER_HOUR",
            )
        if args.service_id == "runpod-pod" and gpu_utilization_pct is None:
            raise ProviderMetricsError(
                "RUNPOD_GPU_UTILIZATION_UNAVAILABLE",
                "nvidia-smi returned no valid utilization sample during inference",
            )
        rtf = processing_duration / audio_duration
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
            "rtf": rtf,
            "rtfx": audio_duration / processing_duration,
            "rtf_scope": "model",
            "cer": jiwer.cer(reference_text, hypothesis_text) if reference_text else None,
            "peak_vram_bytes": torch.cuda.max_memory_allocated() if device.type == "cuda" else None,
            "gpu_utilization_pct": gpu_utilization_pct,
            "gpu_price_per_hour": gpu_price_per_hour,
            "cost_per_audio_hour": gpu_price_per_hour * rtf if gpu_price_per_hour is not None else None,
        }
    except Exception as exc:
        result = {
            "schema_version": 1,
            "run_id": args.run_id,
            "status": "blocked",
            "error_code": getattr(exc, "error_code", "BENCHMARK_INFERENCE_FAILED"),
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
