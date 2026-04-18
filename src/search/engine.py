"""Search orchestration: tokenizer + repositories."""

from __future__ import annotations

from src.indexer.tokenizer import tokenize
from src.storage.repositories import SearchRepository


class SearchEngine:
    def __init__(self, search_repo: SearchRepository) -> None:
        self._repo = search_repo

    def search(self, query: str) -> list[tuple[str, str, int]]:
        term_ids = self._repo.resolve_term_ids(tokenize(query))
        if not term_ids:
            return []
        rows = self._repo.candidate_pages_for_term_ids(term_ids, limit=50)
        return [(r["url"], r["origin_url"], r["depth"]) for r in rows]
