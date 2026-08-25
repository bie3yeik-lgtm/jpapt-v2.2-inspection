from __future__ import annotations

import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark_runner import pytorch_profiler  # noqa: E402


class FakeKeyAverages:
    def __init__(self, table: str) -> None:
        self._table = table

    def table(self, *, sort_by: str, row_limit: int) -> str:
        self.last_sort_by = sort_by
        self.last_row_limit = row_limit
        return self._table


class FakeProfiler:
    def __init__(self, table: str) -> None:
        self._table = table

    def __enter__(self) -> FakeProfiler:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        return False

    def key_averages(self) -> FakeKeyAverages:
        return FakeKeyAverages(self._table)


class PyTorchProfilerTests(unittest.TestCase):
    def test_enabled_flag(self) -> None:
        with mock.patch.dict("os.environ", {"RTF_PYTORCH_PROFILER": "1"}, clear=False):
            self.assertTrue(pytorch_profiler.pytorch_profiler_enabled())
        with mock.patch.dict("os.environ", {"RTF_PYTORCH_PROFILER": "0"}, clear=False):
            self.assertFalse(pytorch_profiler.pytorch_profiler_enabled())

    def test_build_activities_cpu_only(self) -> None:
        class FakeCuda:
            @staticmethod
            def is_available() -> bool:
                return False

        class FakeProfilerActivity:
            CPU = "cpu"
            CUDA = "cuda"

        class FakeProfilerModule:
            ProfilerActivity = FakeProfilerActivity

        class FakeTorch:
            profiler = FakeProfilerModule()
            cuda = FakeCuda()

        class FakeDevice:
            type = "cpu"

        activities = pytorch_profiler.build_profiler_activities(FakeTorch(), FakeDevice())
        self.assertEqual(activities, ["cpu"])

    def test_emit_profiler_summary_writes_markers_and_file(self) -> None:
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            summary_path = Path(tmp_dir) / "pytorch-profiler-summary.txt"
            with redirect_stdout(buffer):
                pytorch_profiler.emit_profiler_summary("aten::linear\n", summary_path=summary_path)
            output = buffer.getvalue()
            self.assertIn(pytorch_profiler.PROFILER_TABLE_BEGIN, output)
            self.assertIn("aten::linear", output)
            self.assertIn(pytorch_profiler.PROFILER_TABLE_END, output)
            self.assertEqual(summary_path.read_text(encoding="utf-8"), "aten::linear\n")

    def test_run_representative_profile_invokes_transcribe(self) -> None:
        class FakeProfilerActivity:
            CPU = "cpu"
            CUDA = "cuda"

        class FakeProfilerModule:
            ProfilerActivity = FakeProfilerActivity

            @staticmethod
            def profile(**kwargs: object) -> FakeProfiler:
                return FakeProfiler("aten::matmul\n")

        class FakeCuda:
            @staticmethod
            def is_available() -> bool:
                return True

            @staticmethod
            def synchronize() -> None:
                return None

        class FakeTorch:
            profiler = FakeProfilerModule()
            cuda = FakeCuda()

        class FakeDevice:
            type = "cuda"

        model = object()
        calls: list[tuple[object, tuple[str, ...]]] = []

        def fake_transcribe(model_arg: object, paths: list[str], **kwargs: object) -> list[str]:
            calls.append((model_arg, tuple(paths)))
            return ["mock"]

        table = pytorch_profiler.run_representative_profile(
            torch_module=FakeTorch(),
            device=FakeDevice(),
            transcribe=fake_transcribe,
            model=model,
            audio_paths=["/tmp/sample.wav"],
        )
        self.assertEqual(table, "aten::matmul\n")
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], model)
        self.assertEqual(calls[0][1], ("/tmp/sample.wav",))


if __name__ == "__main__":
    unittest.main()
