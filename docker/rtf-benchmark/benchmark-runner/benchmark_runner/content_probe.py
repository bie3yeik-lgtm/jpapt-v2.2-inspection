"""Run the smallest provider-side inference and persist its content evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from benchmark_runner.transcribe_compat import transcribe


def _failure_code(exc: Exception) -> tuple[str, str]:
    message = str(exc)
    if any(
        marker in message.lower()
        for marker in (
            "driver on your system is too old",
            "cuda driver version is insufficient",
            "nvidia driver on your system is too old",
        )
    ):
        return (
            "PROVIDER_CUDA_DRIVER_INCOMPATIBLE",
            "benchmark image CUDA runtime is incompatible with the provider NVIDIA driver",
        )
    return "PROVIDER_CONTENT_PROBE_FAILED", message


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="benchmark-content-probe")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-revision", required=True)
    parser.add_argument("--decoder", required=True)
    parser.add_argument("--precision", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--service-id", required=True)
    parser.add_argument("--gpu", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--fixture-repo-id", required=True)
    parser.add_argument("--fixture-revision", required=True)
    return parser.parse_args()


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError("manifest contains no samples")
    sample = json.loads(lines[0])
    if not isinstance(sample, dict):
        raise ValueError("first manifest line is not an object")
    audio_path = sample.get("audio_path")
    if not isinstance(audio_path, str) or not Path(audio_path).is_file():
        raise ValueError("first manifest audio_path is not a materialized local file")
    return sample, hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RTF_CONTENT_PROBE=" + json.dumps(payload, sort_keys=True), flush=True)


def main() -> int:
    args = _args()
    sample, local_manifest_sha256 = _load_manifest(args.manifest)
    manifest_sha256 = os.environ.get("RTF_FIXTURE_MANIFEST_SHA256", local_manifest_sha256)
    base: dict[str, Any] = {
        "schema_version": 1,
        "run_id": args.run_id,
        "status": "blocked",
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "dataset_id": args.dataset_id,
        "dataset_revision": args.dataset_revision,
        "decoder": args.decoder,
        "precision": args.precision,
        "provider": args.provider,
        "environment": "linux",
        "service_id": args.service_id,
        "gpu": args.gpu,
        "image_digest": os.environ.get("RTF_IMAGE_DIGEST", ""),
        "inspection_profile": args.profile,
        "fixture_repo_id": args.fixture_repo_id,
        "fixture_revision": args.fixture_revision,
        "manifest_sha256": manifest_sha256,
        "sample_index": 0,
        "audio_path": sample.get("audio_path"),
        "reference_text": str(sample.get("text", "")),
    }
    try:
        import torch
        from huggingface_hub import snapshot_download
        from nemo.collections.asr.models import ASRModel

        if args.provider == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA provider requested but torch.cuda.is_available() is false")
        device = torch.device("cuda" if args.provider == "cuda" else "cpu")
        model_dir = Path(snapshot_download(
            repo_id=args.model_id,
            revision=args.model_revision,
            token=os.environ.get("HF_TOKEN"),
            allow_patterns=["*.nemo", "*.json", "*.yaml"],
        ))
        nemo_files = sorted(model_dir.glob("*.nemo"))
        if not nemo_files:
            raise RuntimeError(f"no .nemo model was found in pinned snapshot: {model_dir}")
        model = ASRModel.restore_from(restore_path=str(nemo_files[0]), map_location=device)
        model = model.to(device).eval()
        with torch.inference_mode():
            hypotheses = transcribe(
                model,
                [str(sample["audio_path"])],
                batch_size=1,
                torch_module=torch,
                device=device,
            )
        item = hypotheses[0]
        text = str(item.text if hasattr(item, "text") else item)
        base.update({
            "status": "completed",
            "hypothesis_text": text,
            "content_available": True,
        })
    except Exception as exc:
        error_code, error_message = _failure_code(exc)
        base.update({
            "error_code": error_code,
            "error_message": error_message,
            "content_available": False,
        })
    output = args.output
    _write(output, base)
    return 0 if base["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
