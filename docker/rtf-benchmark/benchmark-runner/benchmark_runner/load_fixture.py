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
    manifest = Path(hf_hub_download(
        repo_id=args.repo_id,
        repo_type="dataset",
        filename=args.filename,
        revision=args.revision,
    ))
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if args.expected_manifest_sha256 and manifest_sha256 != args.expected_manifest_sha256:
        raise ValueError("fixture manifest SHA-256 does not match the resolver receipt")
    args.audio_dir.mkdir(parents=True, exist_ok=True)
    records = []
    names: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        record = json.loads(line)
        source = str(record["audio_path"])
        name = Path(source).name
        if name in names:
            raise ValueError(f"fixture contains duplicate audio filename: {name}")
        names.add(name)
        local = Path(hf_hub_download(
            repo_id=args.repo_id,
            repo_type="dataset",
            filename=source,
            revision=args.revision,
        ))
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
