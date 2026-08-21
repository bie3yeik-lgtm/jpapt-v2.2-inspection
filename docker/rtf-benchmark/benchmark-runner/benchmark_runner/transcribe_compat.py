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


def _set_config_value(config: Any, name: str, value: Any) -> bool:
    """Set a field on a NeMo transcription config when that field exists."""

    if hasattr(config, name):
        setattr(config, name, value)
        return True
    try:
        if name in config:
            config[name] = value
            return True
    except (TypeError, KeyError):
        pass
    return False


def _patch_loader_factory(model: Any) -> tuple[Any, Any]:
    """Force loader policy even on NeMo versions that hard-code pin_memory.

    Several NeMo ASR implementations build the temporary transcription loader
    with ``pin_memory=True`` regardless of the public transcribe arguments.
    The policy is therefore supplied before construction and the resulting
    loader is only inspected.  PyTorch does not allow all DataLoader
    attributes (notably ``persistent_workers``) to be changed after
    initialization, so post-construction mutation would make the provider
    fail before the first sample is read.
    """

    original = getattr(model, "_setup_transcribe_dataloader", None)
    if original is None:
        return None, None
    had_instance_attribute = "_setup_transcribe_dataloader" in vars(model)

    def constrained(config: Any) -> Any:
        effective_config = dict(config)
        effective_config["num_workers"] = 0
        effective_config["pin_memory"] = False
        loader = original(effective_config)
        if getattr(loader, "num_workers", 0) != 0 or getattr(loader, "pin_memory", False):
            raise RuntimeError("NeMo transcription DataLoader policy was not applied")
        return loader

    setattr(model, "_setup_transcribe_dataloader", constrained)
    return original, had_instance_attribute


def _restore_loader_factory(model: Any, original: Any, had_instance_attribute: Any) -> None:
    if original is None:
        return
    if had_instance_attribute:
        setattr(model, "_setup_transcribe_dataloader", original)
    else:
        delattr(model, "_setup_transcribe_dataloader")


def _build_safe_override_config(model: Any, batch_size: int) -> Any:
    """Build the typed NeMo override config for the provider safety policy."""

    factory = getattr(model, "get_transcribe_config", None)
    if not callable(factory):
        return None
    config = factory()
    _set_config_value(config, "batch_size", batch_size)
    if not _set_config_value(config, "num_workers", 0):
        return None
    # Lhotse is useful for training-scale pipelines but is not required for
    # this materialized benchmark manifest. Prefer the plain ASR dataloader;
    # it avoids the provider image's Lhotse worker/pinned-memory defaults.
    _set_config_value(config, "use_lhotse", False)
    _set_config_value(config, "pin_memory", False)
    return config


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
    original_loader, had_instance_attribute = _patch_loader_factory(model)
    try:
        override_config = _build_safe_override_config(model, batch_size)
        if override_config is not None and _supports_keyword(function, "override_config"):
            kwargs = {"override_config": override_config}
        else:
            if _supports_keyword(function, "num_workers"):
                kwargs["num_workers"] = 0
            if _supports_keyword(function, "pin_memory"):
                kwargs["pin_memory"] = False
            if _supports_keyword(function, "use_lhotse"):
                kwargs["use_lhotse"] = False
        print(
            'RTF_DATALOADER_POLICY={"num_workers":0,"pin_memory":false,"use_lhotse":false}',
            flush=True,
        )
        result = function(list(paths), **kwargs)
    finally:
        _restore_loader_factory(model, original_loader, had_instance_attribute)
    if getattr(device, "type", None) == "cuda":
        torch_module.cuda.synchronize()
    return result
