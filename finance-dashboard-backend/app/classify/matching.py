"""Whole-word, longest-phrase-first matching. No decisions, just finding phrases in token lists."""

import re
from typing import Dict, List, Optional, Sequence, Tuple, TypeVar

V = TypeVar("V")
_TOKEN = re.compile(r"[A-Z0-9]+")


def tokenize(text: str) -> List[str]:
    """'Toast Box @ NEX' -> ['TOAST', 'BOX', 'NEX']. Punctuation separates words; case is ignored."""
    return _TOKEN.findall((text or "").upper())


def find_phrase(tokens: Sequence[str], phrase: Sequence[str]) -> Optional[int]:
    """Index where `phrase` appears as consecutive whole words in `tokens`, else None."""
    n = len(phrase)
    if n == 0 or n > len(tokens):
        return None
    for i in range(len(tokens) - n + 1):
        if list(tokens[i : i + n]) == list(phrase):
            return i
    return None


def build_index(phrases: Dict[str, V]) -> Dict[Tuple[str, ...], V]:
    return {tuple(tokenize(p)): v for p, v in phrases.items() if tokenize(p)}


def best_match(tokens: Sequence[str], index: Dict[Tuple[str, ...], V]):
    """
    The longest phrase from `index` found in `tokens` (earliest wins a tie), as
    (phrase_tokens, value, position), or None. Longest-first is what makes AMAZON PRIME beat
    AMAZON and GRABFOOD beat GRAB.
    """
    best = None
    for phrase, value in index.items():
        position = find_phrase(tokens, phrase)
        if position is None:
            continue
        rank = (len(phrase), sum(len(t) for t in phrase), -position)
        if best is None or rank > best[0]:
            best = (rank, phrase, value, position)
    return None if best is None else (best[1], best[2], best[3])