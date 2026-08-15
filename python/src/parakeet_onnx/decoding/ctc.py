from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import numpy.typing as npt


def ctc_collapse(
    token_ids: Iterable[int],
    *,
    blank_id: int,
) -> list[int]:
    result: list[int] = []
    previous: int | None = None
    for raw in token_ids:
        token = int(raw)
        if token != previous and token != blank_id:
            result.append(token)
        previous = token
    return result


def greedy_ctc_ids(
    logits: npt.NDArray[np.floating],
    *,
    blank_id: int,
) -> list[int] | list[list[int]]:
    values = np.asarray(logits)
    if values.ndim == 2:
        return ctc_collapse(np.argmax(values, axis=-1), blank_id=blank_id)
    if values.ndim == 3:
        return [
            ctc_collapse(row, blank_id=blank_id)
            for row in np.argmax(values, axis=-1)
        ]
    raise ValueError(
        f"CTC logits must have rank 2 or 3; got shape={values.shape!r}"
    )
