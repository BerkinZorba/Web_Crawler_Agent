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
from src.indexer.indexer import Indexer, PageIndexInput
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

    def test_search_results_are_url_origin_depth_triples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "s.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://site.test/", 1)
                pid = repos.pages.save_fetched_page(
                    run_id,
                    url="https://site.test/doc",
                    origin_url="https://site.test/",
                    depth=2,
                    title=None,
                    content_text="giraffe",
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                    indexed_status="not_indexed",
                )
                tid = repos.index.get_or_create_term("giraffe")
                repos.index.replace_page_terms(pid, [(tid, 1, 0)])
                repos.index.set_page_indexed_status(pid, "indexed")
                out = SearchEngine(repos.search).search("giraffe")
                self.assertEqual(len(out), 1)
                trip = out[0]
                self.assertIsInstance(trip, tuple)
                self.assertEqual(len(trip), 3)
                url, origin_url, depth = trip
                self.assertIsInstance(url, str)
                self.assertIsInstance(origin_url, str)
                self.assertIsInstance(depth, int)
                self.assertEqual(url, "https://site.test/doc")
                self.assertEqual(origin_url, "https://site.test/")
                self.assertEqual(depth, 2)

    def test_indexing_status_index_failed_not_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "s.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://ex.test/", 1)
                pid = repos.pages.save_fetched_page(
                    run_id,
                    url="https://ex.test/broken",
                    origin_url="https://ex.test/",
                    depth=0,
                    title=None,
                    content_text="yak",
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                    indexed_status="index_failed",
                )
                tid = repos.index.get_or_create_term("yak")
                repos.index.replace_page_terms(pid, [(tid, 3, 0)])
                eng = SearchEngine(repos.search)
                self.assertEqual(eng.search("yak"), [])

    def test_end_to_end_save_indexer_search_triple(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "s.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://e2e.test/", 2)
                pid = repos.pages.save_fetched_page(
                    run_id,
                    url="https://e2e.test/page",
                    origin_url="https://e2e.test/",
                    depth=1,
                    title="About badgers",
                    content_text="badgers are furry",
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                    indexed_status="not_indexed",
                )
                indexer = Indexer(repos.index)
                self.assertTrue(
                    indexer.index_page(
                        PageIndexInput(
                            page_id=pid,
                            title="About badgers",
                            content_text="badgers are furry",
                        )
                    )
                )
                out = SearchEngine(repos.search).search("badgers")
                self.assertEqual(len(out), 1)
                self.assertEqual(
                    out[0],
                    ("https://e2e.test/page", "https://e2e.test/", 1),
                )

    def test_mid_indexing_status_not_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "s.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://mid.test/", 1)
                pid = repos.pages.save_fetched_page(
                    run_id,
                    url="https://mid.test/p",
                    origin_url="https://mid.test/",
                    depth=0,
                    title=None,
                    content_text="mushroom",
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                    indexed_status="not_indexed",
                )
                tid = repos.index.get_or_create_term("mushroom")
                repos.index.replace_page_terms(pid, [(tid, 4, 0)])
                repos.index.set_page_indexed_status(pid, "indexing")
                self.assertEqual(SearchEngine(repos.search).search("mushroom"), [])

    def test_only_indexed_page_returned_when_pair_shares_term(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "s.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://pair.test/", 1)
                tid = repos.index.get_or_create_term("otter")
                for path, status in (("/hidden", "not_indexed"), ("/public", "indexed")):
                    pid = repos.pages.save_fetched_page(
                        run_id,
                        url=f"https://pair.test{path}",
                        origin_url="https://pair.test/",
                        depth=0,
                        title=None,
                        content_text="x",
                        http_status=200,
                        fetch_status="ok",
                        fetched_at="2026-01-01 00:00:00",
                        indexed_status="not_indexed",
                    )
                    repos.index.replace_page_terms(pid, [(tid, 1, 0)])
                    repos.index.set_page_indexed_status(pid, status)
                out = SearchEngine(repos.search).search("otter")
                self.assertEqual(len(out), 1)
                self.assertEqual(out[0][0], "https://pair.test/public")

    def test_search_correctness_empty_safe_and_triple_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "s.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                eng = SearchEngine(repos.search)
                self.assertEqual(eng.search(None), [])
                run_id = repos.crawl_runs.create("https://fmt.test/", 1)
                pid = repos.pages.save_fetched_page(
                    run_id,
                    url="https://fmt.test/z",
                    origin_url="https://fmt.test/",
                    depth=3,
                    title=None,
                    content_text="pangolin scales",
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                    indexed_status="not_indexed",
                )
                t1 = repos.index.get_or_create_term("pangolin")
                t2 = repos.index.get_or_create_term("scales")
                repos.index.replace_page_terms(pid, [(t1, 1, 0), (t2, 1, 0)])
                repos.index.set_page_indexed_status(pid, "indexed")
                rows = eng.search("pangolin")
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(len(row), 3)
                self.assertIsInstance(row[0], str)
                self.assertIsInstance(row[1], str)
                self.assertIsInstance(row[2], int)

    def test_cross_run_same_url_both_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "s.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                shared_url = "https://dup.test/same-doc"
                tid = repos.index.get_or_create_term("quokka")
                indexer = Indexer(repos.index)
                for origin in ("https://alpha.test/", "https://beta.test/"):
                    rid = repos.crawl_runs.create(origin, 1)
                    pid = repos.pages.save_fetched_page(
                        rid,
                        url=shared_url,
                        origin_url=origin,
                        depth=0,
                        title=None,
                        content_text="quokka happy",
                        http_status=200,
                        fetch_status="ok",
                        fetched_at="2026-01-01 00:00:00",
                        indexed_status="not_indexed",
                    )
                    self.assertTrue(
                        indexer.index_page(
                            PageIndexInput(
                                page_id=pid,
                                title=None,
                                content_text="quokka happy",
                            )
                        )
                    )
                out = SearchEngine(repos.search).search("quokka")
                self.assertEqual(len(out), 2)
                self.assertEqual(
                    {r[0] for r in out},
                    {shared_url},
                )
                self.assertEqual(
                    {r[1] for r in out},
                    {"https://alpha.test/", "https://beta.test/"},
                )


if __name__ == "__main__":
    unittest.main()
