"""Download an immutable benchmark fixture from a Hugging Face Dataset repo."""

from __future__ import annotations

import argparse
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
    args = parser.parse_args()
    manifest = Path(hf_hub_download(
        repo_id=args.repo_id,
        repo_type="dataset",
        filename=args.filename,
        revision=args.revision,
    ))
    args.audio_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        record = json.loads(line)
        source = str(record["audio_path"])
        local = Path(hf_hub_download(
            repo_id=args.repo_id,
            repo_type="dataset",
            filename=source,
            revision=args.revision,
        ))
        target = args.audio_dir / Path(source).name
        target.write_bytes(local.read_bytes())
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
