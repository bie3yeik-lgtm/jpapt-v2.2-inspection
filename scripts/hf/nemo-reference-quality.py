#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, hf_hub_download

MODEL_REPO = "nvidia/parakeet-tdt_ctc-0.6b-ja"
MODEL_FILE = "parakeet-tdt_ctc-0.6b-ja.nemo"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def transcribed_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    text = getattr(value, "text", None)
    if isinstance(text, str):
        return text
    if isinstance(value, (tuple, list)) and len(value) == 1:
        return transcribed_text(value[0])
    raise TypeError(f"unsupported NeMo transcription result type: {type(value)!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-repo", default=MODEL_REPO)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--resolved-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--decoder", choices=["ctc"], default="ctc")
    parser.add_argument("--batch-size", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.model_repo != MODEL_REPO:
        raise SystemExit(f"model_repo must be exactly {MODEL_REPO}")
    if args.batch_size <= 0:
        raise SystemExit("batch-size must be positive")

    manifest = json.loads(args.resolved_manifest.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise SystemExit("resolved manifest schema_version must be 1")
    samples = manifest.get("samples")
    if not isinstance(samples, list) or not samples:
        raise SystemExit("resolved manifest samples must be a non-empty array")
    if manifest.get("expected_sample_count") != len(samples):
        raise SystemExit("resolved manifest expected_sample_count mismatch")

    api = HfApi()
    info = api.model_info(args.model_repo, revision=args.model_revision)
    revision = info.sha
    if not isinstance(revision, str) or len(revision) < 40:
        raise SystemExit("failed to resolve immutable model revision")

    model_path = Path(
        hf_hub_download(
            repo_id=args.model_repo,
            filename=MODEL_FILE,
            revision=revision,
        )
    )
    model_sha = sha256_file(model_path)

    import torch
    from nemo.collections.asr.models import ASRModel

    model = ASRModel.restore_from(restore_path=str(model_path), map_location="cpu")
    model.eval()
    model.change_decoding_strategy(decoder_type="ctc")

    audio_paths: list[str] = []
    for sample in samples:
        path = sample.get("audio_path")
        audio_sha = sample.get("audio_sha256")
        if not isinstance(path, str) or not path:
            raise SystemExit(f"sample {sample.get('id')} has no materialized audio_path")
        if not isinstance(audio_sha, str) or len(audio_sha) != 64:
            raise SystemExit(f"sample {sample.get('id')} has no exact audio_sha256")
        local_audio = Path(path)
        if not local_audio.is_file():
            raise SystemExit(f"materialized audio file is missing: {path}")
        if sha256_file(local_audio) != audio_sha:
            raise SystemExit(f"audio SHA mismatch before NeMo inference: {sample.get('id')}")
        audio_paths.append(path)

    with torch.inference_mode():
        outputs = model.transcribe(audio=audio_paths, batch_size=args.batch_size)
    if len(outputs) != len(samples):
        raise SystemExit("NeMo transcribe output count mismatch")

    evidence_samples: list[dict[str, Any]] = []
    for sample, output in zip(samples, outputs, strict=True):
        text = transcribed_text(output)
        evidence_samples.append(
            {
                "id": sample["id"],
                "audio_sha256": sample["audio_sha256"],
                "reference_text": sample["transcription"],
                "text": text,
                "normalized_text": normalize_text(text),
            }
        )

    document = {
        "schema_version": 1,
        "reference_run_id": f"nemo-{revision[:12]}-{args.decoder}",
        "source": {
            "repo_id": args.model_repo,
            "revision_resolved": revision,
            "model_file": MODEL_FILE,
            "model_file_sha256": model_sha,
            "library": "nemo",
            "language": "ja",
            "license": "cc-by-4.0",
        },
        "decoder": args.decoder,
        "normalization": "asr_metrics_v1",
        "samples": evidence_samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"reference_run_id": document["reference_run_id"], "samples": len(samples), "model_revision": revision}, sort_keys=True))


if __name__ == "__main__":
    main()
