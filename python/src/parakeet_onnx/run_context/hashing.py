"""
Hashing utilities used by RunContext generation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


_DEFAULT_CHUNK_SIZE = 1024 * 1024


def sha256_file(
    path: str | Path,
    *,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> str:
    """
    Calculate SHA-256 for a file without loading it entirely into memory.

    This is important for ONNX candidates that may be hundreds of MB.
    """

    file_path = Path(path)

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Cannot hash missing file: {file_path}"
        )

    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()
