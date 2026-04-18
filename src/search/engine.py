"""Search orchestration: tokenizer + repositories (TODO)."""

from __future__ import annotations

from src.indexer.tokenizer import tokenize
from src.storage.repositories import SearchRepository


class SearchEngine:
    def __init__(self, search_repo: SearchRepository) -> None:
        self._repo = search_repo

    def search(self, query: str) -> list[tuple[str, str, int]]:
        # TODO: return list of (relevant_url, origin_url, depth) for indexed pages only.
        _ = tokenize(query)
        _ = self._repo.search_placeholder(query)
        raise NotImplementedError
