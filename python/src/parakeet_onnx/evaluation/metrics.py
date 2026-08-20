from __future__ import annotations

import unicodedata
from dataclasses import dataclass


def normalize_text(text: str) -> str:
    """Minimal deterministic normalization for metric comparison.

    Dataset-specific normalization policy should eventually be revision
    controlled by evaluation-schema.json. This baseline intentionally avoids
    language-specific heuristics.
    """
    return " ".join(unicodedata.normalize("NFKC", text).strip().split())


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    if not reference:
        return len(hypothesis)
    if not hypothesis:
        return len(reference)

    previous = list(range(len(hypothesis) + 1))
    for i, ref_item in enumerate(reference, start=1):
        current = [i]
        for j, hyp_item in enumerate(hypothesis, start=1):
            substitution = previous[j - 1] + (ref_item != hyp_item)
            insertion = current[j - 1] + 1
            deletion = previous[j] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    ref = list(normalize_text(reference))
    hyp = list(normalize_text(hypothesis))
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = normalize_text(reference).split()
    hyp = normalize_text(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


@dataclass(frozen=True, slots=True)
class CorpusErrorAccumulator:
    character_edits: int = 0
    reference_characters: int = 0
    word_edits: int = 0
    reference_words: int = 0

    def add(self, reference: str, hypothesis: str) -> CorpusErrorAccumulator:
        ref_text = normalize_text(reference)
        hyp_text = normalize_text(hypothesis)
        ref_chars = list(ref_text)
        hyp_chars = list(hyp_text)
        ref_words = ref_text.split()
        hyp_words = hyp_text.split()
        return CorpusErrorAccumulator(
            character_edits=(self.character_edits + edit_distance(ref_chars, hyp_chars)),
            reference_characters=(self.reference_characters + len(ref_chars)),
            word_edits=self.word_edits + edit_distance(ref_words, hyp_words),
            reference_words=self.reference_words + len(ref_words),
        )

    @property
    def cer(self) -> float | None:
        if self.reference_characters == 0:
            return None
        return self.character_edits / self.reference_characters

    @property
    def wer(self) -> float | None:
        if self.reference_words == 0:
            return None
        return self.word_edits / self.reference_words
