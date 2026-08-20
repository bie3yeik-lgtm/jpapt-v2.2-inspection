from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import numpy as np

StateT = TypeVar("StateT")


@dataclass(frozen=True, slots=True)
class TdtDecoderConfig:
    blank_id: int
    bos_id: int
    durations: tuple[int, ...]
    max_symbols_per_step: int = 10

    def __post_init__(self) -> None:
        if not self.durations:
            raise ValueError("TDT duration vocabulary must not be empty")
        if any(value < 0 for value in self.durations):
            raise ValueError("TDT durations must be non-negative")
        if self.max_symbols_per_step < 1:
            raise ValueError("max_symbols_per_step must be >= 1")


@dataclass(frozen=True, slots=True)
class TdtDecodeResult:
    token_ids: list[int]
    frame_positions: list[int]
    durations: list[int]


def greedy_tdt_decode[StateT](
    encoder_frames: np.ndarray,
    *,
    config: TdtDecoderConfig,
    initial_state: StateT,
    predictor_step: Callable[[int, StateT], tuple[np.ndarray, StateT]],
    joint_step: Callable[[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]],
) -> TdtDecodeResult:
    """Greedy token-and-duration transducer decoding.

    The function intentionally knows nothing about ONNX tensor names. Predictor
    recurrent state and joint-network execution are supplied by callbacks so the
    same algorithm can be used with ORT, a reference implementation, or unit-test
    doubles.

    The joint callback returns separate token and duration logits. The duration
    argmax indexes `config.durations`. A duration of zero is legal for token
    emission, but blank/non-emission always advances by at least one frame to
    guarantee progress.
    """

    frames = np.asarray(encoder_frames)
    if frames.ndim == 3:
        if frames.shape[0] != 1:
            raise ValueError("greedy TDT decoder supports batch size 1")
        frames = frames[0]
    if frames.ndim != 2:
        raise ValueError(f"encoder_frames must have rank 2/3, got {frames.shape!r}")

    time_steps = int(frames.shape[0])
    state = initial_state
    last_token = config.bos_id
    emitted: list[int] = []
    positions: list[int] = []
    emitted_durations: list[int] = []

    t = 0
    symbols_at_t = 0
    while t < time_steps:
        predictor, next_state = predictor_step(last_token, state)
        token_logits, duration_logits = joint_step(frames[t], predictor)
        token_values = np.asarray(token_logits).reshape(-1)
        duration_values = np.asarray(duration_logits).reshape(-1)
        if duration_values.size != len(config.durations):
            raise ValueError(
                "TDT duration logits size does not match duration vocabulary: "
                f"{duration_values.size} != {len(config.durations)}"
            )

        token_id = int(np.argmax(token_values))
        duration = int(config.durations[int(np.argmax(duration_values))])

        if token_id == config.blank_id:
            t += max(1, duration)
            symbols_at_t = 0
            continue

        emitted.append(token_id)
        positions.append(t)
        emitted_durations.append(duration)
        last_token = token_id
        state = next_state
        symbols_at_t += 1

        if duration > 0:
            t += duration
            symbols_at_t = 0
        elif symbols_at_t >= config.max_symbols_per_step:
            t += 1
            symbols_at_t = 0

    return TdtDecodeResult(
        token_ids=emitted,
        frame_positions=positions,
        durations=emitted_durations,
    )


def decode_tdt(*args: object, **kwargs: object) -> TdtDecodeResult:
    """Compatibility name for the implemented greedy TDT decoder."""

    return greedy_tdt_decode(*args, **kwargs)  # type: ignore[arg-type]
