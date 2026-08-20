from __future__ import annotations

from pathlib import Path

from .finalize import finalize_candidate_variant


def export_ctc_candidate(
    *,
    output_dir: Path,
    tokenizer_path: str | None = None,
    profile_set: str = "parakeet-tdt-ctc-v1",
    variant: str = "ctc",
) -> Path:
    """Finalize an already-exported CTC graph using the minimal candidate contract."""

    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "model.onnx"
    if not model_path.is_file():
        raise RuntimeError(f"No exported model exists at {model_path}. Run the pinned export adapter first.")
    finalize_candidate_variant(
        output_dir=root,
        profile_set=profile_set,
        variant=variant,
        artifact_roles={"primary": model_path.name},
        tokenizer_path=tokenizer_path,
    )
    return model_path
