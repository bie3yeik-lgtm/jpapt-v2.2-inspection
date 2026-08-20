from __future__ import annotations

from parakeet_onnx.datasets.models import DatasetRecord
from parakeet_onnx.datasets.resolver import DatasetBackend


class FakeBackend(DatasetBackend):
    def iter_records(self, lock):
        for index in range(10):
            yield DatasetRecord(
                identity=f"id:{index}",
                index=index,
                duration_sec=1.0 + index * 0.1,
                sample_rate_hz=16_000,
                transcription=f"sample-{index}",
                audio=None,
            )


def test_fake_backend_contract() -> None:
    backend = FakeBackend()
    assert isinstance(backend, DatasetBackend)
