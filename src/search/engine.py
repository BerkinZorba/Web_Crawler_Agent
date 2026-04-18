"""Search: tokenize query, load indexed candidates from SQLite, rank, return triples."""

from __future__ import annotations

from src.indexer.ranking import score_page
from src.indexer.tokenizer import tokenize
from src.storage.repositories import SearchRepository

_DEFAULT_RESULT_LIMIT = 50


class SearchEngine:
    def __init__(self, search_repo: SearchRepository) -> None:
        self._repo = search_repo

    def search(self, query: str | None) -> list[tuple[str, str, int]]:
        """
        Return ranked ``(relevant_url, origin_url, depth)`` for fully indexed pages only.

        Empty list when the query is missing/blank, tokenizes to nothing, or matches no
        known terms / no indexed pages. Never raises for normal user input.
        """
        if query is None:
            return []
        q = str(query).strip()
        if not q:
            return []

        try:
            tokens = tokenize(q)
        except Exception:
            return []

        if not tokens:
            return []

        try:
            term_ids = self._repo.resolve_term_ids(tokens)
        except Exception:
            return []

        if not term_ids:
            return []

        try:
            rows = self._repo.indexed_candidate_stats_for_term_ids(term_ids)
        except Exception:
            return []

        scored: list[tuple[float, str, str, int]] = []
        for r in rows:
            try:
                s = score_page(
                    matched_distinct_terms=int(r["matched_distinct"]),
                    body_frequency_sum=int(r["body_sum"]),
                    title_frequency_sum=int(r["title_sum"]),
                    depth=int(r["depth"]),
                )
            except ValueError:
                continue
            scored.append(
                (
                    s,
                    str(r["url"]),
                    str(r["origin_url"]),
                    int(r["depth"]),
                )
            )

        scored.sort(key=lambda t: (-t[0], t[1]))
        return [(u, o, d) for _, u, o, d in scored[:_DEFAULT_RESULT_LIMIT]]
