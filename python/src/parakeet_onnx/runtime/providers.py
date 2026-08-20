from __future__ import annotations

_PROVIDER_NAMES = {
    "cpu": "CPUExecutionProvider",
    "cuda": "CUDAExecutionProvider",
    "directml": "DmlExecutionProvider",
    "coreml": "CoreMLExecutionProvider",
}


class ProviderResolutionError(RuntimeError):
    pass


def available_provider_names() -> tuple[str, ...]:
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise ProviderResolutionError("onnxruntime is required for runtime provider inspection.") from exc
    return tuple(ort.get_available_providers())


def resolve_provider_chain(
    provider_id: str,
    *,
    allow_cpu_fallback: bool = True,
) -> list[str]:
    try:
        requested = _PROVIDER_NAMES[provider_id]
    except KeyError as exc:
        raise ProviderResolutionError(f"unsupported provider id: {provider_id!r}") from exc

    available = set(available_provider_names())
    if requested not in available:
        raise ProviderResolutionError(f"{requested} is not available; available={sorted(available)!r}")

    chain = [requested]
    if allow_cpu_fallback and requested != "CPUExecutionProvider" and "CPUExecutionProvider" in available:
        chain.append("CPUExecutionProvider")
    return chain
