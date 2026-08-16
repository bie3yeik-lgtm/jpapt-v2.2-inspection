from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .metadata import (
    ArtifactMetadata,
    CandidateMetadata,
    TokenizerMetadata,
    write_candidate_metadata,
)
from .validate import validate_onnx_model


def load_runtime_contract(path: str | Path) -> dict[str, Any]:
    value_path = Path(path).expanduser().resolve()
    raw = json.loads(value_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("runtime contract JSON root must be an object")
    for key in ("decoder", "input_kind", "io", "decoder_config"):
        if key not in raw:
            raise ValueError(f"runtime contract is missing required field: {key}")
    return raw


def finalize_candidate(
    *,
    output_dir: Path,
    candidate_id: str,
    decoder: str,
    artifact_contract: str,
    artifact_roles: dict[str, str],
    runtime_contract: dict[str, Any],
    tokenizer_kind: str | None = None,
    tokenizer_path: str | None = None,
    features: dict[str, bool] | None = None,
) -> CandidateMetadata:
    root = Path(output_dir).expanduser().resolve()
    if runtime_contract.get("decoder") != decoder:
        raise ValueError("runtime contract decoder does not match candidate decoder")

    artifacts: dict[str, ArtifactMetadata] = {}
    for role, relative in artifact_roles.items():
        path = (root / relative).resolve()
        path.relative_to(root)
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() == ".onnx":
            validate_onnx_model(path)
        artifacts[role] = ArtifactMetadata.from_file(path, relative_to=root)

    tokenizer: TokenizerMetadata | None = None
    if tokenizer_kind is not None or tokenizer_path is not None:
        if tokenizer_kind is None or tokenizer_path is None:
            raise ValueError("tokenizer_kind and tokenizer_path must be supplied together")
        resolved = (root / tokenizer_path).resolve()
        resolved.relative_to(root)
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        tokenizer = TokenizerMetadata(kind=tokenizer_kind, path=tokenizer_path)

    metadata = CandidateMetadata(
        candidate_id=candidate_id,
        decoder=decoder,
        artifact_contract=artifact_contract,
        artifacts=artifacts,
        runtime_contract=runtime_contract,
        tokenizer=tokenizer,
        features=dict(features or {}),
    )
    write_candidate_metadata(root / "metadata.json", metadata)
    return metadata
