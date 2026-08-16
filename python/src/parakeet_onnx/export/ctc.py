from __future__ import annotations

from pathlib import Path

from .finalize import finalize_candidate, load_runtime_contract


def export_ctc_candidate(
    *,
    output_dir: Path,
    candidate_id: str,
    runtime_contract_path: Path | None = None,
    tokenizer_path: str = "vocabulary.json",
) -> Path:
    """Finalize an already-exported CTC ONNX graph as a canonical candidate.

    The framework-specific exporter must place `model.onnx` and a runtime
    contract JSON in the staging directory. The finalizer never guesses tensor
    names or blank IDs: those are part of the candidate runtime contract.
    """

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
    if runtime_contract.get("decoder") != "ctc":
        raise RuntimeError("CTC finalizer requires runtime contract decoder='ctc'")

    finalize_candidate(
        output_dir=root,
        candidate_id=candidate_id,
        decoder="ctc",
        artifact_contract="ctc-single-graph-v1",
        artifact_roles={"primary": model_path.name},
        runtime_contract=runtime_contract,
        tokenizer_kind="vocabulary",
        tokenizer_path=tokenizer_path,
        features={
            "kv_cache": False,
            "multi_graph": False,
            "transformers_processor": False,
            "external_frontend": runtime_contract.get("input_kind") == "features",
            "timestamps": False,
        },
    )
    return model_path
