from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .providers import resolve_provider_chain


@dataclass(frozen=True, slots=True)
class OrtSessionConfig:
    model_path: Path
    provider_id: str = "cpu"
    allow_cpu_fallback: bool = True
    provider_options: dict[str, dict[str, Any]] = field(default_factory=dict)


def create_session(config: OrtSessionConfig):
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError(
            "onnxruntime is required. Install the appropriate project extra."
        ) from exc

    model_path = Path(config.model_path).expanduser().resolve()
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    providers = resolve_provider_chain(
        config.provider_id,
        allow_cpu_fallback=config.allow_cpu_fallback,
    )

    options = [
        config.provider_options.get(provider, {})
        for provider in providers
    ]

    session_options = ort.SessionOptions()
    return ort.InferenceSession(
        str(model_path),
        sess_options=session_options,
        providers=providers,
        provider_options=options,
    )
