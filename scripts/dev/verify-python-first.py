#!/usr/bin/env python3
from __future__ import annotations

import compileall
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    paths = [
        root / "python" / "src",
        root / "scripts" / "ci",
        root / "scripts" / "dev",
    ]

    ok = True
    for path in paths:
        if path.exists():
            ok = (
                compileall.compile_dir(
                    str(path),
                    quiet=1,
                    force=True,
                )
                and ok
            )

    resolver = root / "python/src/parakeet_onnx/datasets/resolver.py"
    text = resolver.read_text(encoding="utf-8")
    if "\t" in text:
        print(
            "ERROR: resolver.py still contains tab indentation.",
            file=sys.stderr,
        )
        ok = False

    print("python-first verification:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
