"""Materialize the locked Common Voice subset into the runner manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import numpy as np
import soundfile as sf
from datasets import Audio, load_dataset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--configuration", default="default")
    parser.add_argument("--split", default="test")
    parser.add_argument("--count-min", type=int, default=20)
    parser.add_argument("--count-max", type=int, default=50)
    parser.add_argument("--target-total-sec", type=float, default=5400.0)
    parser.add_argument("--max-duration-sec", type=float, default=600.0)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.dataset_id != "japanese-asr/ja_asr.common_voice_8_0":
        raise SystemExit("only the locked Common Voice dataset is supported")
    dataset = load_dataset(
        args.dataset_id,
        name=args.configuration,
        split=args.split,
        revision=args.revision,
    ).cast_column("audio", Audio(sampling_rate=16_000))
    rng = random.Random(args.seed)
    candidates = list(range(len(dataset)))
    rng.shuffle(candidates)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    if args.count_min < 1 or args.count_max < args.count_min:
        raise ValueError("invalid sample count bounds")
    chunk_target_sec = max(30.0, min(args.max_duration_sec, args.target_total_sec / args.count_min))
    pending_audio: list[object] = []
    pending_text: list[str] = []
    pending_duration = 0.0

    def flush() -> None:
        nonlocal pending_audio, pending_text, pending_duration
        if pending_duration < 30.0:
            return
        path = args.output_dir / f"{len(records):04d}.wav"
        import numpy as np

        merged = np.concatenate([np.asarray(part, dtype=np.float32) for part in pending_audio])
        sf.write(path, merged, 16_000, subtype="PCM_16")
        records.append({
            "dataset_id": args.dataset_id,
            "dataset_revision": args.revision,
            "audio_path": str(path.resolve()),
            "audio_duration_sec": pending_duration,
            "text": " ".join(pending_text),
            "audio_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
        pending_audio, pending_text, pending_duration = [], [], 0.0

    for index in candidates:
        row = dataset[index]
        audio = row["audio"]
        array = np.asarray(audio["array"], dtype=np.float32)
        if array.ndim == 2:
            array = array.mean(axis=1)
        if array.ndim != 1 or not np.isfinite(array).all():
            continue
        duration = len(array) / 16_000
        if duration <= 0:
            continue
        if pending_duration >= 30.0 and pending_duration + duration > chunk_target_sec:
            flush()
        pending_audio.append(array)
        pending_text.append(str(row.get("sentence", "")))
        pending_duration += duration
        if (
            pending_duration >= 30.0
            and len(records) >= args.count_min - 1
            and sum(r["audio_duration_sec"] for r in records) + pending_duration >= args.target_total_sec
        ):
            flush()
            break
    flush()
    total_duration = sum(float(r["audio_duration_sec"]) for r in records)
    if not args.count_min <= len(records) <= args.count_max:
        raise RuntimeError(f"materialized {len(records)} samples; required {args.count_min}..{args.count_max}")
    if total_duration < args.target_total_sec:
        raise RuntimeError(f"materialized {total_duration:.2f}s; required {args.target_total_sec:.2f}s")
    args.manifest.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
