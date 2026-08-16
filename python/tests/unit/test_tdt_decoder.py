from __future__ import annotations

import numpy as np

from parakeet_onnx.decoding.tdt import TdtDecoderConfig, greedy_tdt_decode


def test_greedy_tdt_emits_tokens_and_advances_by_duration() -> None:
    frames = np.zeros((4, 3), dtype=np.float32)
    calls = {"joint": 0}

    def predictor_step(token: int, state: tuple[int, ...]):
        return np.asarray([token], dtype=np.float32), state + (token,)

    def joint_step(frame: np.ndarray, prediction: np.ndarray):
        del frame, prediction
        calls["joint"] += 1
        if calls["joint"] == 1:
            return np.asarray([0.0, 5.0, -1.0]), np.asarray([0.0, 4.0])
        return np.asarray([5.0, 0.0, -1.0]), np.asarray([4.0, 0.0])

    result = greedy_tdt_decode(
        frames,
        config=TdtDecoderConfig(
            blank_id=0,
            bos_id=2,
            durations=(0, 2),
            max_symbols_per_step=4,
        ),
        initial_state=(),
        predictor_step=predictor_step,
        joint_step=joint_step,
    )

    assert result.token_ids == [1]
    assert result.frame_positions == [0]
    assert result.durations == [2]
    assert calls["joint"] == 3


def test_blank_with_zero_duration_always_makes_progress() -> None:
    frames = np.zeros((3, 2), dtype=np.float32)
    calls = 0

    def predictor_step(token: int, state: None):
        del token
        return np.zeros((1,), dtype=np.float32), state

    def joint_step(frame: np.ndarray, prediction: np.ndarray):
        nonlocal calls
        del frame, prediction
        calls += 1
        return np.asarray([9.0, 0.0]), np.asarray([9.0])

    result = greedy_tdt_decode(
        frames,
        config=TdtDecoderConfig(blank_id=0, bos_id=1, durations=(0,)),
        initial_state=None,
        predictor_step=predictor_step,
        joint_step=joint_step,
    )

    assert result.token_ids == []
    assert calls == 3


def test_zero_duration_token_is_bounded_by_max_symbols_per_step() -> None:
    frames = np.zeros((2, 2), dtype=np.float32)
    calls = 0

    def predictor_step(token: int, state: None):
        del token
        return np.zeros((1,), dtype=np.float32), state

    def joint_step(frame: np.ndarray, prediction: np.ndarray):
        nonlocal calls
        del frame, prediction
        calls += 1
        return np.asarray([0.0, 9.0]), np.asarray([9.0])

    result = greedy_tdt_decode(
        frames,
        config=TdtDecoderConfig(
            blank_id=0,
            bos_id=1,
            durations=(0,),
            max_symbols_per_step=2,
        ),
        initial_state=None,
        predictor_step=predictor_step,
        joint_step=joint_step,
    )

    assert result.token_ids == [1, 1, 1, 1]
    assert calls == 4
