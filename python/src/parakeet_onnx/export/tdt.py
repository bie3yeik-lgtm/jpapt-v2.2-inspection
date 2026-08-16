from __future__ import annotations

from pathlib import Path

from .finalize import finalize_candidate_variant, load_runtime_contract


def export_tdt_candidate(
    *,
    output_dir: Path,
    candidate_id: str,
    runtime_contract_path: Path | None = None,
    tokenizer_path: str = "vocabulary.json",
    profile_set: str = "parakeet-tdt-ctc-v1",
    variant: str = "tdt",
) -> tuple[Path, Path, Path]:
    """Finalize encoder/predictor/joint TDT graphs as one candidate variant."""

    root = Path(output_dir).expanduser().resolve()
    paths = (
        root / "encoder.onnx",
        root / "predictor.onnx",
        root / "joint.onnx",
    )
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(
            "TDT finalization requires encoder.onnx, predictor.onnx, and joint.onnx; "
            f"missing={missing}"
        )
    contract_path = (
        runtime_contract_path.expanduser().resolve()
        if runtime_contract_path is not None
        else root / "runtime-contract.json"
    )
    runtime_contract = load_runtime_contract(contract_path)

    finalize_candidate_variant(
        output_dir=root,
        candidate_id=candidate_id,
        profile_set=profile_set,
        variant=variant,
        artifact_roles={
            "encoder": "encoder.onnx",
            "predictor": "predictor.onnx",
            "joint": "joint.onnx",
        },
        runtime_contract=runtime_contract,
        tokenizer_path=tokenizer_path,
    )
    return paths
