"""Simple word tokenization for keyword index (TODO: normalize case, strip noise)."""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    # TODO: lowercase, stopwords optional, unicode folding if needed.
    return [m.group(0).lower() for m in _WORD.finditer(text or "")]
