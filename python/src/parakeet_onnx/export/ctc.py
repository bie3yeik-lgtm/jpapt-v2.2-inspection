from __future__ import annotations

from pathlib import Path

from .finalize import finalize_candidate_variant, load_runtime_contract


def export_ctc_candidate(
    *,
    output_dir: Path,
    candidate_id: str,
    runtime_contract_path: Path | None = None,
    tokenizer_path: str = "vocabulary.json",
    profile_set: str = "parakeet-tdt-ctc-v1",
    variant: str = "ctc",
) -> Path:
    """Finalize an already-exported CTC graph as one candidate variant."""

    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "model.onnx"
    if not model_path.is_file():
        raise RuntimeError(
            f"No exported model exists at {model_path}. Run the pinned export adapter first."
        )
    contract_path = (
        runtime_contract_path.expanduser().resolve()
        if runtime_contract_path is not None
        else root / "runtime-contract.json"
    )
    if not contract_path.is_file():
        raise RuntimeError(
            "CTC finalization requires runtime-contract.json so tensor names and "
            "blank_id are never guessed."
        )
    runtime_contract = load_runtime_contract(contract_path)

    finalize_candidate_variant(
        output_dir=root,
        candidate_id=candidate_id,
        profile_set=profile_set,
        variant=variant,
        artifact_roles={"primary": model_path.name},
        runtime_contract=runtime_contract,
        tokenizer_path=tokenizer_path,
    )
    return model_path
