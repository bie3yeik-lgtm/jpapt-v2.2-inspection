#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

from parakeet_onnx.config.resolver import ConfigResolver
from parakeet_onnx.hf.targets import HfTargetError, load_hf_target


def main() -> int:
    root = Path(".").resolve()
    target_root = root / "config" / "hf-targets"

    if not target_root.is_dir():
        print("ERROR: config/hf-targets is missing.", file=sys.stderr)
        return 1

    resolver = ConfigResolver(root)
    failures = 0

    for path in sorted(target_root.glob("*.toml")):
        try:
            target = load_hf_target(path)
            model = resolver.load_model(target.model_id)

            if model.upstream_repo_id != target.upstream_repo_id:
                raise HfTargetError(
                    "upstream repo mismatch: "
                    f"{model.upstream_repo_id!r} != "
                    f"{target.upstream_repo_id!r}"
                )

            framework = model.get("model.framework")
            if framework != target.canonical_framework:
                raise HfTargetError(
                    "framework mismatch: "
                    f"{framework!r} != {target.canonical_framework!r}"
                )

            model_decoders = model.get("decoders.supported", [])
            if model_decoders:
                missing = set(target.supported_decoders) - set(model_decoders)
                if missing:
                    raise HfTargetError(
                        f"target decoders missing from model config: {sorted(missing)!r}"
                    )

            print(
                f"OK {target.id}: "
                f"{target.upstream_repo_id} -> "
                f"{target.model_repo} / {target.bucket}"
            )
        except Exception as exc:
            failures += 1
            print(f"ERROR {path}: {exc}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
