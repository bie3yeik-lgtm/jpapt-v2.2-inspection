from __future__ import annotations

from pathlib import Path

from .finalize import finalize_candidate, load_runtime_contract


def export_tdt_candidate(
    *,
    output_dir: Path,
    candidate_id: str,
    runtime_contract_path: Path | None = None,
    tokenizer_path: str = "vocabulary.json",
) -> tuple[Path, Path, Path]:
    """Finalize encoder/predictor/joint TDT graphs as one candidate bundle."""

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
    if runtime_contract.get("decoder") != "tdt":
        raise RuntimeError("TDT finalizer requires runtime contract decoder='tdt'")

    finalize_candidate(
        output_dir=root,
        candidate_id=candidate_id,
        decoder="tdt",
        artifact_contract="tdt-multi-graph-v1",
        artifact_roles={
            "encoder": "encoder.onnx",
            "predictor": "predictor.onnx",
            "joint": "joint.onnx",
        },
        runtime_contract=runtime_contract,
        tokenizer_kind="vocabulary",
        tokenizer_path=tokenizer_path,
        features={
            "kv_cache": False,
            "multi_graph": True,
            "transformers_processor": False,
            "external_frontend": runtime_contract.get("input_kind") == "features",
            "timestamps": False,
        },
    )
    return paths
