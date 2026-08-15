from __future__ import annotations

from pathlib import Path

from parakeet_onnx.runtime import OrtSessionConfig, create_session


def validate_onnx_model(path: Path) -> dict[str, object]:
    model_path = Path(path).expanduser().resolve()
    try:
        import onnx
    except ImportError as exc:
        raise RuntimeError("onnx is required for structural validation.") from exc

    model = onnx.load(str(model_path))
    onnx.checker.check_model(model)

    session = create_session(
        OrtSessionConfig(
            model_path=model_path,
            provider_id="cpu",
            allow_cpu_fallback=False,
        )
    )

    return {
        "path": str(model_path),
        "providers": session.get_providers(),
        "inputs": [item.name for item in session.get_inputs()],
        "outputs": [item.name for item in session.get_outputs()],
    }
