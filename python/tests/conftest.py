from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"

    (root / "config").mkdir(parents=True)
    (root / "evaluation" / "schemas").mkdir(parents=True)
    (root / "evaluation" / "manifests").mkdir(parents=True)
    (root / "evaluation" / "expected").mkdir(parents=True)
    (root / "python" / "src" / "parakeet_onnx").mkdir(parents=True)

    (root / "pyproject.toml").write_text(
        "[project]\nname='parakeet-onnx-test'\nversion='0.0.0'\n",
        encoding="utf-8",
    )

    return root


@pytest.fixture()
def mono_wav_16k(tmp_path: Path) -> Path:
    path = tmp_path / "mono.wav"
    sr = 16_000
    t = np.arange(sr, dtype=np.float32) / sr
    audio = 0.25 * np.sin(2.0 * np.pi * 440.0 * t)
    sf.write(path, audio, sr, subtype="FLOAT")
    return path


@pytest.fixture()
def stereo_wav_48k(tmp_path: Path) -> Path:
    path = tmp_path / "stereo.wav"
    sr = 48_000
    t = np.arange(sr, dtype=np.float32) / sr
    left = 0.25 * np.sin(2.0 * np.pi * 440.0 * t)
    right = 0.10 * np.sin(2.0 * np.pi * 880.0 * t)
    audio = np.stack([left, right], axis=1).astype(np.float32)
    sf.write(path, audio, sr, subtype="FLOAT")
    return path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
