"""Download an immutable benchmark fixture from a Hugging Face Dataset repo."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import hf_hub_download


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--filename", default="benchmark-v1.jsonl")
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    manifest = Path(
        hf_hub_download(
            repo_id=args.repo_id,
            repo_type="dataset",
            filename=args.filename,
            revision=args.revision,
        )
    )
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if args.expected_manifest_sha256 and manifest_sha256 != args.expected_manifest_sha256:
        raise ValueError("fixture manifest SHA-256 does not match the resolver receipt")
    args.audio_dir.mkdir(parents=True, exist_ok=True)
    records = []
    names: set[str] = set()
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        record = json.loads(line)
        # The locked Common Voice dataset names its transcript `sentence`,
        # while the RTF fixture contract names the canonical field `text`.
        # Normalize this at the fixture boundary so CER is computed from the
        # dataset reference rather than silently becoming null.
        reference = record.get("text")
        if not isinstance(reference, str) or not reference.strip():
            for candidate in ("sentence", "transcription", "reference_text"):
                value = record.get(candidate)
                if isinstance(value, str) and value.strip():
                    reference = value
                    break
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError(f"fixture line {line_number} has no non-empty reference transcript")
        record["text"] = reference
        source = str(record["audio_path"])
        name = Path(source).name
        if name in names:
            raise ValueError(f"fixture contains duplicate audio filename: {name}")
        names.add(name)
        local = Path(
            hf_hub_download(
                repo_id=args.repo_id,
                repo_type="dataset",
                filename=source,
                revision=args.revision,
            )
        )
        target = args.audio_dir / name
        target.write_bytes(local.read_bytes())
        expected_sha = record.get("audio_sha256")
        actual_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        if expected_sha and actual_sha != expected_sha:
            raise ValueError(f"audio SHA-256 mismatch for {source}")
        record["audio_path"] = str(target)
        records.append(record)
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
