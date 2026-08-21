"""NeMo transcription compatibility and CUDA stability boundary."""

from __future__ import annotations

import inspect
import os
from collections.abc import Sequence
from typing import Any


def configure_cuda_diagnostics(torch_module: Any) -> None:
    """Enable deterministic CUDA diagnostics only for an explicit diagnostic run."""

    if os.environ.get("RTF_CUDA_DIAGNOSTICS", "0") not in {"1", "true", "TRUE"}:
        return
    os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "1")
    os.environ.setdefault("TORCH_SHOW_CPP_STACKTRACES", "1")
    if hasattr(torch_module, "cuda") and torch_module.cuda.is_available():
        torch_module.cuda.synchronize()


def _supports_keyword(function: Any, name: str) -> bool:
    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == name or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def transcribe(
    model: Any,
    paths: Sequence[str],
    *,
    batch_size: int,
    torch_module: Any,
    device: Any,
) -> Any:
    """Call the installed NeMo API with conservative loader settings.

    NeMo releases do not expose an identical ``transcribe`` signature. The
    worker and pinned-memory controls are therefore passed only when the
    installed API accepts them. Setting zero workers and disabling pinned
    memory avoids the allocator path that caused the observed T4 illegal
    memory access while preserving the benchmark batch-size contract.
    """

    configure_cuda_diagnostics(torch_module)
    function = model.transcribe
    kwargs: dict[str, Any] = {"batch_size": batch_size}
    if _supports_keyword(function, "num_workers"):
        kwargs["num_workers"] = int(os.environ.get("RTF_NUM_WORKERS", "0"))
    if _supports_keyword(function, "pin_memory"):
        kwargs["pin_memory"] = False
    result = function(list(paths), **kwargs)
    if getattr(device, "type", None) == "cuda":
        torch_module.cuda.synchronize()
    return result
