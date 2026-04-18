"""Write tokens to SQLite and flip indexed_status (TODO)."""

from __future__ import annotations

from src.storage.repositories import IndexRepository, PageRepository


class Indexer:
    def __init__(self, pages: PageRepository, index: IndexRepository) -> None:
        self._pages = pages
        self._index = index

    def index_page(self, page_id: int, title: str, body: str) -> None:
        # TODO: tokenize title/body, upsert page_terms, set indexed_status='indexed'.
        raise NotImplementedError
