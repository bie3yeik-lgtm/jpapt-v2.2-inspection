#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    resolver = root / "python/src/parakeet_onnx/datasets/resolver.py"

    text = resolver.read_text(encoding="utf-8")

    import_line = "from .materializer import DatasetMaterializer\n"
    if import_line not in text:
        marker = "from .manifest import (\n"
        index = text.find(marker)
        if index < 0:
            raise RuntimeError("Could not locate resolver import block.")
        text = text[:index] + import_line + text[index:]

    # Normalize the malformed materializer block found in the current repo.
    pattern = re.compile(
        r"\n[ \t]*materialized = self\.materializer\.materialize\(\n"
        r"[ \t]*record=record,\n"
        r"[ \t]*dataset_revision=lock\.revision,\n"
        r"[ \t]*\)\n"
    )
    replacement = (
        "\n            materialized = self.materializer.materialize(\n"
        "                record=record,\n"
        "                dataset_revision=lock.revision,\n"
        "            )\n"
    )
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError("Could not uniquely locate the materializer block in resolver.py.")

    text = re.sub(
        r"\n[ \t]*audio_path=materialized\.audio_path,\n"
        r"[ \t]*audio_sha256=materialized\.sha256,",
        "\n                    audio_path=materialized.audio_path,"
        "\n                    audio_sha256=materialized.sha256,",
        text,
        count=1,
    )

    resolver.write_text(text, encoding="utf-8")
    print(f"patched: {resolver}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
