from __future__ import annotations

from pathlib import Path

from .finalize import finalize_candidate_variant, load_runtime_contract


def export_whisper_candidate(
    *,
    output_dir: Path,
    candidate_id: str,
    runtime_contract_path: Path | None = None,
    processor_path: str = "tokenizer",
    profile_set: str = "whisper-autoregressive-v1",
    variant: str = "whisper",
) -> tuple[Path, ...]:
    """Finalize Whisper encoder/decoder graphs as one candidate variant."""

    root = Path(output_dir).expanduser().resolve()
    encoder = root / "encoder.onnx"
    decoder = root / "decoder.onnx"
    if not encoder.is_file() or not decoder.is_file():
        raise RuntimeError(
            "Whisper finalization requires encoder.onnx and decoder.onnx"
        )
    contract_path = (
        runtime_contract_path.expanduser().resolve()
        if runtime_contract_path is not None
        else root / "runtime-contract.json"
    )
    runtime_contract = load_runtime_contract(contract_path)

    roles = {"encoder": "encoder.onnx", "decoder": "decoder.onnx"}
    with_past = root / "decoder_with_past.onnx"
    io = runtime_contract.get("io", {})
    requires_with_past = isinstance(io, dict) and "decoder_with_past" in io
    if with_past.is_file():
        roles["decoder_with_past"] = with_past.name
    elif requires_with_past:
        raise RuntimeError(
            "runtime contract defines decoder_with_past but decoder_with_past.onnx is missing"
        )

    finalize_candidate_variant(
        output_dir=root,
        candidate_id=candidate_id,
        profile_set=profile_set,
        variant=variant,
        artifact_roles=roles,
        runtime_contract=runtime_contract,
        tokenizer_path=processor_path,
    )
    return tuple(root / relative for relative in roles.values())
