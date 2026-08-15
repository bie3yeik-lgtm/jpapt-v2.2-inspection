from __future__ import annotations

import json
from pathlib import Path


class VocabularyTokenizer:
    """Dependency-free token ID -> string adapter.

    This supports candidate bundles that include a simple JSON token mapping.
    SentencePiece/NeMo tokenization should be added by a model-specific adapter
    rather than guessed here.
    """

    def __init__(self, id_to_token: dict[int, str]) -> None:
        self.id_to_token = dict(id_to_token)

    @classmethod
    def from_json(cls, path: str | Path) -> "VocabularyTokenizer":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(raw, list):
            mapping = {index: str(token) for index, token in enumerate(raw)}
        elif isinstance(raw, dict):
            mapping = {int(key): str(value) for key, value in raw.items()}
        else:
            raise ValueError("vocabulary JSON must be a list or object")
        return cls(mapping)

    def ids_to_text(self, token_ids: list[int]) -> str:
        return "".join(self.id_to_token[token_id] for token_id in token_ids)
