from __future__ import annotations

from pathlib import Path

from .finalize import finalize_candidate_variant


def export_tdt_candidate(
    *,
    output_dir: Path,
    tokenizer_path: str | None = None,
    profile_set: str = "parakeet-tdt-ctc-v1",
    variant: str = "tdt",
) -> tuple[Path, Path, Path]:
    """Finalize encoder/predictor/joint TDT graphs using minimal metadata."""

    root = Path(output_dir).expanduser().resolve()
    paths = (root / "encoder.onnx", root / "predictor.onnx", root / "joint.onnx")
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(
            "TDT finalization requires encoder.onnx, predictor.onnx, and joint.onnx; "
            f"missing={missing}"
        )
    finalize_candidate_variant(
        output_dir=root,
        profile_set=profile_set,
        variant=variant,
        artifact_roles={
            "encoder": "encoder.onnx",
            "predictor": "predictor.onnx",
            "joint": "joint.onnx",
        },
        tokenizer_path=tokenizer_path,
    )
    return paths
