"""Search/index tests: tokenizer, ranking, and SearchEngine."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.indexer.ranking import (
    DEPTH_PENALTY_PER_LEVEL,
    WEIGHT_BODY_FREQUENCY,
    WEIGHT_DISTINCT_QUERY_TERM,
    WEIGHT_TITLE_FREQUENCY,
    score_page,
)
from src.indexer.tokenizer import token_counts, tokenize
from src.search.engine import SearchEngine
from src.storage.db import connect
from src.storage.repositories import Repositories


class SearchTests(unittest.TestCase):
    def test_tokenize_basic(self) -> None:
        self.assertEqual(tokenize("Hello, world!"), ["hello", "world"])

    def test_tokenize_drops_stopwords_and_short_tokens(self) -> None:
        self.assertEqual(tokenize("The and OR a I x running"), ["running"])

    def test_token_counts(self) -> None:
        self.assertEqual(token_counts(tokenize("cat cat dog")), {"cat": 2, "dog": 1})

    def test_score_page_formula(self) -> None:
        # 2 distinct, body 10, title 1, depth 2
        # -> 5*2 + 1*10 + 3*1 - 0.2*2 = 10 + 10 + 3 - 0.4 = 22.6
        s = score_page(
            matched_distinct_terms=2,
            body_frequency_sum=10,
            title_frequency_sum=1,
            depth=2,
        )
        self.assertAlmostEqual(
            s,
            WEIGHT_DISTINCT_QUERY_TERM * 2
            + WEIGHT_BODY_FREQUENCY * 10
            + WEIGHT_TITLE_FREQUENCY * 1
            - DEPTH_PENALTY_PER_LEVEL * 2,
        )

    def test_score_page_rejects_negative_inputs(self) -> None:
        with self.assertRaises(ValueError):
            score_page(
                matched_distinct_terms=-1,
                body_frequency_sum=0,
                title_frequency_sum=0,
                depth=0,
            )

    def test_search_engine_empty_and_stopword_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "s.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                eng = SearchEngine(repos.search)
                self.assertEqual(eng.search(None), [])
                self.assertEqual(eng.search(""), [])
                self.assertEqual(eng.search("   "), [])
                self.assertEqual(eng.search("the a an"), [])

    def test_search_engine_excludes_not_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "s.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://ex.test/", 1)
                pid = repos.pages.save_fetched_page(
                    run_id,
                    url="https://ex.test/hidden",
                    origin_url="https://ex.test/",
                    depth=0,
                    title=None,
                    content_text="zebra",
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                    indexed_status="not_indexed",
                )
                tid = repos.index.get_or_create_term("zebra")
                repos.index.replace_page_terms(pid, [(tid, 5, 0)])
                eng = SearchEngine(repos.search)
                self.assertEqual(eng.search("zebra"), [])

    def test_search_engine_ranking_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "s.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://ex.test/", 1)
                tid = repos.index.get_or_create_term("python")
                for url_suffix, freq, depth in (("a", 1, 0), ("b", 5, 0)):
                    pid = repos.pages.save_fetched_page(
                        run_id,
                        url=f"https://ex.test/{url_suffix}",
                        origin_url="https://ex.test/",
                        depth=depth,
                        title=None,
                        content_text="x",
                        http_status=200,
                        fetch_status="ok",
                        fetched_at="2026-01-01 00:00:00",
                        indexed_status="not_indexed",
                    )
                    repos.index.replace_page_terms(pid, [(tid, freq, 0)])
                    repos.index.set_page_indexed_status(pid, "indexed")
                eng = SearchEngine(repos.search)
                out = eng.search("python")
                self.assertEqual(len(out), 2)
                self.assertEqual(out[0][0], "https://ex.test/b")
                self.assertEqual(out[1][0], "https://ex.test/a")


if __name__ == "__main__":
    unittest.main()
