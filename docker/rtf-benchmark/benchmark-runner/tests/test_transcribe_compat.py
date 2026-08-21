from __future__ import annotations

import os
import unittest

from benchmark_runner.transcribe_compat import transcribe


class _Cuda:
    def __init__(self) -> None:
        self.sync_count = 0

    def is_available(self) -> bool:
        return True

    def synchronize(self) -> None:
        self.sync_count += 1


class _Torch:
    def __init__(self) -> None:
        self.cuda = _Cuda()


class _Device:
    type = "cuda"


class _ModelWithLoaderControls:
    def __init__(self) -> None:
        self.call: tuple[list[str], dict[str, object]] | None = None

    def transcribe(
        self,
        paths: list[str],
        *,
        batch_size: int,
        num_workers: int = 8,
        pin_memory: bool = True,
    ) -> list[str]:
        self.call = (paths, {
            "batch_size": batch_size,
            "num_workers": num_workers,
            "pin_memory": pin_memory,
        })
        return ["ok"]


class _ModelWithoutLoaderControls:
    def __init__(self) -> None:
        self.call: tuple[list[str], dict[str, object]] | None = None

    def transcribe(self, paths: list[str], *, batch_size: int) -> list[str]:
        self.call = (paths, {"batch_size": batch_size})
        return ["ok"]


class TranscribeCompatTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("RTF_NUM_WORKERS", None)
        os.environ.pop("RTF_CUDA_DIAGNOSTICS", None)

    def test_disables_workers_and_pinned_memory_when_supported(self) -> None:
        os.environ["RTF_NUM_WORKERS"] = "0"
        model = _ModelWithLoaderControls()
        torch = _Torch()

        result = transcribe(
            model,
            ["sample.wav"],
            batch_size=8,
            torch_module=torch,
            device=_Device(),
        )

        self.assertEqual(result, ["ok"])
        assert model.call is not None
        self.assertEqual(model.call[1], {
            "batch_size": 8,
            "num_workers": 0,
            "pin_memory": False,
        })
        self.assertEqual(torch.cuda.sync_count, 1)

    def test_does_not_pass_unsupported_keywords(self) -> None:
        model = _ModelWithoutLoaderControls()
        torch = _Torch()

        transcribe(
            model,
            ["sample.wav"],
            batch_size=1,
            torch_module=torch,
            device=type("CpuDevice", (), {"type": "cpu"})(),
        )

        assert model.call is not None
        self.assertEqual(model.call[1], {"batch_size": 1})

    def test_diagnostic_mode_synchronizes_before_transcription(self) -> None:
        os.environ["RTF_CUDA_DIAGNOSTICS"] = "1"
        model = _ModelWithoutLoaderControls()
        torch = _Torch()

        transcribe(
            model,
            ["sample.wav"],
            batch_size=1,
            torch_module=torch,
            device=_Device(),
        )

        self.assertGreaterEqual(torch.cuda.sync_count, 2)
        self.assertEqual(os.environ["CUDA_LAUNCH_BLOCKING"], "1")


if __name__ == "__main__":
    unittest.main()
