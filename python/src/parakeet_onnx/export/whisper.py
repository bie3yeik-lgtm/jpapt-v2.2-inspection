from __future__ import annotations

from pathlib import Path

from .finalize import finalize_candidate_variant


def export_whisper_candidate(
    *,
    output_dir: Path,
    processor_path: str | None = None,
    profile_set: str = "whisper-autoregressive-v1",
    variant: str = "whisper",
) -> tuple[Path, ...]:
    """Finalize Whisper encoder/decoder graphs using minimal metadata."""

    root = Path(output_dir).expanduser().resolve()
    encoder = root / "encoder.onnx"
    decoder = root / "decoder.onnx"
    if not encoder.is_file() or not decoder.is_file():
        raise RuntimeError("Whisper finalization requires encoder.onnx and decoder.onnx")

    roles = {"encoder": "encoder.onnx", "decoder": "decoder.onnx"}
    with_past = root / "decoder_with_past.onnx"
    if with_past.is_file():
        roles["decoder_with_past"] = with_past.name

    finalize_candidate_variant(
        output_dir=root,
        profile_set=profile_set,
        variant=variant,
        artifact_roles=roles,
        tokenizer_path=processor_path,
    )
    return tuple(root / relative for relative in roles.values())
