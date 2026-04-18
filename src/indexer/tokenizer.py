"""Word tokenization shared by indexing and search (same rules for query and page text)."""

from __future__ import annotations

import re
from typing import Final

# Alphanumeric runs (ASCII letters + digits). Same output shape for page body, titles, and queries.
_TOKEN_RE: Final = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# Drop very short tokens (noise; not useful for keyword index).
MIN_TOKEN_LENGTH: Final = 2

# Small static list — easy to list in README/demo. Applied to queries and documents alike.
STOP_WORDS: Final = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "as",
        "by",
        "from",
        "with",
        "is",
        "was",
        "are",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "what",
        "which",
        "who",
        "whom",
        "if",
        "than",
        "then",
        "so",
        "not",
        "no",
    }
)


def tokenize(text: str) -> list[str]:
    """
    Split text into normalized tokens.

    Rules (identical for user queries and page text):
    - case-fold to lowercase
    - take contiguous runs of ASCII letters and digits
    - drop tokens shorter than :data:`MIN_TOKEN_LENGTH`
    - drop common English stop words (see :data:`STOP_WORDS`)

    Empty or whitespace-only input yields an empty list.
    """
    if not text:
        return []
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(0).lower()
        if len(tok) < MIN_TOKEN_LENGTH:
            continue
        if tok in STOP_WORDS:
            continue
        out.append(tok)
    return out


def token_counts(tokens: list[str]) -> dict[str, int]:
    """Count occurrences per token (for building body frequencies during indexing)."""
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    return counts
