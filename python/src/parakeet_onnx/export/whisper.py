from __future__ import annotations

from pathlib import Path

from .finalize import finalize_candidate, load_runtime_contract


def export_whisper_candidate(
    *,
    output_dir: Path,
    candidate_id: str,
    runtime_contract_path: Path | None = None,
    processor_path: str = "tokenizer",
) -> tuple[Path, ...]:
    """Finalize Whisper encoder/decoder graphs as one candidate bundle.

    `decoder_with_past.onnx` is optional only when the runtime contract does not
    define `io.decoder_with_past`. New production candidates should normally
    include it so KV-cache generation is available.
    """

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
    if runtime_contract.get("decoder") != "whisper_autoregressive":
        raise RuntimeError(
            "Whisper finalizer requires decoder='whisper_autoregressive'"
        )

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

    features = {
        "kv_cache": "decoder_with_past" in roles,
        "multi_graph": True,
        "transformers_processor": True,
        "external_frontend": True,
        "timestamps": bool(runtime_contract.get("decoder_config", {}).get("timestamps", False))
        if isinstance(runtime_contract.get("decoder_config"), dict)
        else False,
    }
    finalize_candidate(
        output_dir=root,
        candidate_id=candidate_id,
        decoder="whisper_autoregressive",
        artifact_contract="whisper-autoregressive-v1",
        artifact_roles=roles,
        runtime_contract=runtime_contract,
        tokenizer_kind="transformers_processor",
        tokenizer_path=processor_path,
        features=features,
    )
    return tuple(root / relative for relative in roles.values())
