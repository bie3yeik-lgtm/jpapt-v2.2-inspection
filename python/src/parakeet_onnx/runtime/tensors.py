from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TensorMetadata:
    name: str
    type: str
    shape: tuple[Any, ...]


def _metadata(items) -> tuple[TensorMetadata, ...]:
    return tuple(
        TensorMetadata(
            name=item.name,
            type=item.type,
            shape=tuple(item.shape),
        )
        for item in items
    )


def input_metadata(session) -> tuple[TensorMetadata, ...]:
    return _metadata(session.get_inputs())


def output_metadata(session) -> tuple[TensorMetadata, ...]:
    return _metadata(session.get_outputs())
