"""Persist token frequencies for a page and drive ``indexed_status`` transitions.

Callers should run ``index_page`` on the same SQLite connection (and ideally inside a
single transaction opened by the crawl coordinator) so that ``indexing`` → postings →
``indexed`` commits atomically. If the process dies mid-index, the page can remain in
``indexing``; search only returns ``indexed``, so partial postings are never exposed.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.indexer.tokenizer import token_counts, tokenize
from src.storage.repositories import IndexRepository


@dataclass(frozen=True)
class PageIndexInput:
    """Minimal page snapshot needed for indexing (already stored in ``pages``)."""

    page_id: int
    title: str | None = None
    content_text: str | None = None


class Indexer:
    def __init__(self, index: IndexRepository) -> None:
        self._index = index

    def index_page(self, page: PageIndexInput) -> bool:
        """
        Tokenize title and body, write ``terms`` / ``page_terms``, mark page searchable.

        Status flow: ``not_indexed`` (or any prior state) → ``indexing`` → ``indexed``
        on success, or ``index_failed`` if anything goes wrong. Does not raise on
        storage errors so the crawl loop can continue.

        Body hits go to ``frequency``; title-only hits use ``in_title_frequency`` (both
        can be non-zero for the same term).
        """
        pid = page.page_id
        try:
            self._index.set_page_indexed_status(pid, "indexing")

            body_tokens = tokenize(page.content_text or "")
            title_tokens = tokenize(page.title or "")
            body_counts = token_counts(body_tokens)
            title_counts = token_counts(title_tokens)
            all_terms = sorted(set(body_counts) | set(title_counts))

            entries: list[tuple[int, int, int]] = []
            for term in all_terms:
                tid = self._index.get_or_create_term(term)
                body_freq = body_counts.get(term, 0)
                title_freq = title_counts.get(term, 0)
                entries.append((tid, body_freq, title_freq))

            self._index.replace_page_terms(pid, entries)
            self._index.set_page_indexed_status(pid, "indexed")
            return True
        except Exception:
            try:
                self._index.set_page_indexed_status(pid, "index_failed")
            except Exception:
                pass
            return False
