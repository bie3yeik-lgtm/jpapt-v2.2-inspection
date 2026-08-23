from __future__ import annotations

import sys
import types
import unittest

# The metric helper is dependency-free, but importing the CLI also imports
# jiwer. Keep this unit test runnable in the lightweight repository test env.
sys.modules.setdefault("jiwer", types.SimpleNamespace(cer=lambda *_args: 0.0))
from benchmark_runner.cli import median_metric  # noqa: E402


class SequentialMetricTests(unittest.TestCase):
    def test_median_metric_is_p50(self) -> None:
        self.assertEqual(median_metric([0.4, 0.1, 0.3, 0.2, 0.9]), 0.3)

    def test_median_metric_returns_none_without_measurements(self) -> None:
        self.assertIsNone(median_metric([]))


if __name__ == "__main__":
    unittest.main()
