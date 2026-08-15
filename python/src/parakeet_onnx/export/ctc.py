from __future__ import annotations

from pathlib import Path

from .metadata import (
    CandidateMetadata,
    sha256_file,
    write_candidate_metadata,
)
from .validate import validate_onnx_model


def export_ctc_candidate(
    *,
    output_dir: Path,
    candidate_id: str,
) -> Path:
    """Finalize an ONNX file produced by the pinned NeMo export integration.

    This function deliberately does not guess NeMo's version-specific hybrid
    FastConformer export call. Place the exported model at
    `<output_dir>/model.onnx`; this function validates it and writes stable
    candidate metadata. The NeMo-specific export adapter is the next
    implementation step once the pinned container/model revision is resolved.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.onnx"

    if not model_path.is_file():
        raise RuntimeError(
            "No exported model exists at "
            f"{model_path}. Run the pinned NeMo CTC export adapter first."
        )

    validate_onnx_model(model_path)
    metadata = CandidateMetadata(
        schema_version=1,
        candidate_id=candidate_id,
        primary_artifact=model_path.name,
        decoder="ctc",
        artifact_sha256=sha256_file(model_path),
    )
    write_candidate_metadata(output_dir / "metadata.json", metadata)
    return model_path
