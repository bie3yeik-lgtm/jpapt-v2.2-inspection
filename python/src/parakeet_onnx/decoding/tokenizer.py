from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TokenizerAdapter:
    tokenizer: Any

    def ids_to_text(self, token_ids: list[int]) -> str:
        tokenizer = self.tokenizer

        if hasattr(tokenizer, "ids_to_text"):
            return str(tokenizer.ids_to_text(token_ids))

        if hasattr(tokenizer, "decode"):
            return str(tokenizer.decode(token_ids))

        if hasattr(tokenizer, "tokenizer") and hasattr(
            tokenizer.tokenizer, "decode"
        ):
            return str(tokenizer.tokenizer.decode(token_ids))

        raise TypeError(
            "Unsupported tokenizer object: no ids_to_text/decode method."
        )
