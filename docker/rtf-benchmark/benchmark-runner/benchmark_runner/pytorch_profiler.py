"""PyTorch Profiler helpers for RTF benchmark diagnosis.

Profiling runs are intentionally separate from timed RTF measurements. Enable
with ``RTF_PYTORCH_PROFILER=1`` to capture one representative transcribe pass
after the normal benchmark loop completes.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

PROFILER_TABLE_BEGIN = "RTF_PYTORCH_PROFILER_TABLE_BEGIN"
PROFILER_TABLE_END = "RTF_PYTORCH_PROFILER_TABLE_END"
DEFAULT_ROW_LIMIT = 20
DEFAULT_SORT_BY = "cuda_time_total"


def pytorch_profiler_enabled() -> bool:
    return os.environ.get("RTF_PYTORCH_PROFILER", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def profiler_output_dir() -> Path:
    raw = os.environ.get("RTF_PYTORCH_PROFILER_OUTPUT_DIR", "/output/profiler").strip()
    return Path(raw or "/output/profiler")


def profiler_row_limit() -> int:
    raw = os.environ.get("RTF_PYTORCH_PROFILER_ROW_LIMIT", str(DEFAULT_ROW_LIMIT)).strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError("RTF_PYTORCH_PROFILER_ROW_LIMIT must be an integer") from exc
    if parsed <= 0:
        raise ValueError("RTF_PYTORCH_PROFILER_ROW_LIMIT must be positive")
    return parsed


def profiler_sort_by(device_type: str) -> str:
    configured = os.environ.get("RTF_PYTORCH_PROFILER_SORT_BY", "").strip()
    if configured:
        return configured
    return "cpu_time_total" if device_type == "cpu" else DEFAULT_SORT_BY


def build_profiler_activities(torch_module: Any, device: Any) -> list[Any]:
    activities = [torch_module.profiler.ProfilerActivity.CPU]
    if getattr(device, "type", None) == "cuda" and torch_module.cuda.is_available():
        activities.append(torch_module.profiler.ProfilerActivity.CUDA)
    return activities


def format_profiler_table(
    prof: Any,
    *,
    sort_by: str,
    row_limit: int,
) -> str:
    averages = prof.key_averages()
    return averages.table(sort_by=sort_by, row_limit=row_limit)


def emit_profiler_summary(table: str, *, summary_path: Path | None = None) -> None:
    print(PROFILER_TABLE_BEGIN, flush=True)
    print(table, end="" if table.endswith("\n") else "\n", flush=True)
    print(PROFILER_TABLE_END, flush=True)
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(table if table.endswith("\n") else f"{table}\n", encoding="utf-8")


def run_representative_profile(
    *,
    torch_module: Any,
    device: Any,
    transcribe: Callable[..., Any],
    model: Any,
    audio_paths: Sequence[str],
    batch_size: int = 1,
) -> str:
    """Profile one representative transcribe pass outside the timed RTF loop."""

    if not audio_paths:
        raise ValueError("profiler requires at least one audio path")
    activities = build_profiler_activities(torch_module, device)
    sort_by = profiler_sort_by(getattr(device, "type", "cpu"))
    row_limit = profiler_row_limit()
    with torch_module.profiler.profile(
        activities=activities,
        record_shapes=True,
        profile_memory=True,
    ) as prof:
        transcribe(
            model,
            list(audio_paths),
            batch_size=batch_size,
            torch_module=torch_module,
            device=device,
        )
        if getattr(device, "type", None) == "cuda":
            torch_module.cuda.synchronize()
    return format_profiler_table(prof, sort_by=sort_by, row_limit=row_limit)


def run_post_benchmark_profiler(
    *,
    torch_module: Any,
    device: Any,
    transcribe: Callable[..., Any],
    model_loader: Callable[[], Any],
    audio_paths: Sequence[str],
) -> tuple[str, Path]:
    """Load an isolated model and emit one profiling summary artifact."""

    model = model_loader()
    try:
        table = run_representative_profile(
            torch_module=torch_module,
            device=device,
            transcribe=transcribe,
            model=model,
            audio_paths=audio_paths,
        )
    finally:
        del model
    summary_path = profiler_output_dir() / "pytorch-profiler-summary.txt"
    emit_profiler_summary(table, summary_path=summary_path)
    return table, summary_path


def smoke_test() -> int:
    """CPU-only micro profile for CI environments without NeMo or CUDA."""

    import torch

    linear = torch.nn.Linear(32, 32)
    sample = torch.randn(8, 32)
    activities = [torch.profiler.ProfilerActivity.CPU]
    with torch.profiler.profile(
        activities=activities,
        record_shapes=True,
        profile_memory=True,
    ) as prof:
        linear(sample)
    table = format_profiler_table(prof, sort_by="cpu_time_total", row_limit=5)
    emit_profiler_summary(table)
    if PROFILER_TABLE_BEGIN not in table and "aten" not in table:
        # Table headers vary; ensure we produced non-empty profiler output.
        if not table.strip():
            raise RuntimeError("profiler smoke test produced an empty table")
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="benchmark_runner.pytorch_profiler")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="run a CPU-only torch.profiler smoke test for CI",
    )
    args = parser.parse_args()
    if not args.smoke_test:
        parser.error("only --smoke-test is supported outside the benchmark runner")
    return smoke_test()


if __name__ == "__main__":
    raise SystemExit(main())
