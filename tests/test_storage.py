"""Storage: schema bootstrap, frontier dedup, pages, search stats."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.storage.db import connect
from src.storage.repositories import Repositories

_EXPECTED_TABLES = frozenset({"crawl_runs", "frontier", "pages", "terms", "page_terms"})


class StorageTests(unittest.TestCase):
    def test_database_initializes_with_core_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with connect(db_path, with_schema=True) as conn:
                names = {
                    str(r["name"])
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
                self.assertTrue(_EXPECTED_TABLES <= names)

    def test_schema_and_repositories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://example.com/", 2)
                self.assertTrue(repos.frontier.enqueue_origin(run_id, "https://example.com/"))
                page_id = repos.pages.insert_placeholder(
                    run_id, "https://example.com/", "https://example.com/", 0
                )
                term_id = repos.index.get_or_create_term("hello")
                self.assertGreater(run_id, 0)
                self.assertGreater(page_id, 0)
                self.assertGreater(term_id, 0)

    def test_frontier_duplicate_prevention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://example.com/", 2)
                self.assertTrue(
                    repos.frontier.try_enqueue_url(
                        run_id,
                        url="https://example.com/a",
                        origin_url="https://example.com/",
                        depth=1,
                        discovered_from="https://example.com/",
                    )
                )
                self.assertFalse(
                    repos.frontier.try_enqueue_url(
                        run_id,
                        url="https://example.com/a",
                        origin_url="https://example.com/",
                        depth=1,
                        discovered_from="https://example.com/",
                    )
                )
                self.assertTrue(repos.frontier.url_known_for_run(run_id, "https://example.com/a"))

    def test_claim_and_mark_frontier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://example.com/", 2)
                repos.frontier.enqueue_origin(run_id, "https://example.com/")
                entry = repos.frontier.claim_next_queued(run_id)
                self.assertIsNotNone(entry)
                assert entry is not None
                self.assertEqual(entry.url, "https://example.com/")
                row = conn.execute(
                    "SELECT status FROM frontier WHERE id = ?",
                    (entry.id,),
                ).fetchone()
                self.assertEqual(row["status"], "processing")
                repos.frontier.set_frontier_status(entry.id, "done")
                row = conn.execute(
                    "SELECT status FROM frontier WHERE id = ?",
                    (entry.id,),
                ).fetchone()
                self.assertEqual(row["status"], "done")

    def test_save_page_and_search_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://example.com/", 2)
                pid = repos.pages.save_fetched_page(
                    run_id,
                    url="https://example.com/doc",
                    origin_url="https://example.com/",
                    depth=1,
                    title="Hi",
                    content_text="hello world",
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                )
                tid_hello = repos.index.get_or_create_term("hello")
                tid_world = repos.index.get_or_create_term("world")
                repos.index.replace_page_terms(
                    pid,
                    [(tid_hello, 2, 1), (tid_world, 1, 0)],
                )
                repos.index.set_page_indexed_status(pid, "indexed")

                term_ids = repos.search.resolve_term_ids(["hello", "world"])
                self.assertEqual(set(term_ids), {tid_hello, tid_world})
                hits = repos.search.indexed_candidate_stats_for_term_ids(term_ids)
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]["url"], "https://example.com/doc")
                self.assertEqual(hits[0]["origin_url"], "https://example.com/")
                self.assertEqual(hits[0]["depth"], 1)
                self.assertEqual(hits[0]["matched_distinct"], 2)
                self.assertEqual(hits[0]["body_sum"], 3)
                self.assertEqual(hits[0]["title_sum"], 1)

    def test_url_known_when_page_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://example.com/", 2)
                repos.pages.save_fetched_page(
                    run_id,
                    url="https://example.com/only-page",
                    origin_url="https://example.com/",
                    depth=0,
                    title=None,
                    content_text=None,
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                )
                self.assertTrue(
                    repos.frontier.url_known_for_run(run_id, "https://example.com/only-page")
                )

    def test_same_url_same_run_upserts_single_page_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://ex.test/", 1)
                u = "https://ex.test/page"
                pid1 = repos.pages.save_fetched_page(
                    run_id,
                    url=u,
                    origin_url="https://ex.test/",
                    depth=0,
                    title="A",
                    content_text=None,
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                )
                pid2 = repos.pages.save_fetched_page(
                    run_id,
                    url=u,
                    origin_url="https://ex.test/",
                    depth=0,
                    title="B",
                    content_text="x",
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-02 00:00:00",
                )
                self.assertEqual(pid1, pid2)
                n = conn.execute(
                    "SELECT COUNT(*) AS c FROM pages WHERE crawl_run_id = ? AND url = ?",
                    (run_id, u),
                ).fetchone()["c"]
                self.assertEqual(int(n), 1)

    def test_resume_requeues_processing_to_queued(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://resume.test/", 2)
                repos.frontier.enqueue_origin(run_id, "https://resume.test/")
                entry = repos.frontier.claim_next_queued(run_id)
                self.assertIsNotNone(entry)
                self.assertEqual(repos.frontier.count_by_status(run_id, "processing"), 1)
                self.assertEqual(repos.frontier.count_by_status(run_id, "queued"), 0)
                moved = repos.frontier.requeue_stale_processing(run_id)
                self.assertEqual(moved, 1)
                self.assertEqual(repos.frontier.count_by_status(run_id, "queued"), 1)
                self.assertEqual(repos.frontier.count_by_status(run_id, "processing"), 0)

    def test_requeue_all_stale_processing_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                r1 = repos.crawl_runs.create("https://one.test/", 1)
                r2 = repos.crawl_runs.create("https://two.test/", 1)
                repos.frontier.enqueue_origin(r1, "https://one.test/")
                repos.frontier.enqueue_origin(r2, "https://two.test/")
                self.assertIsNotNone(repos.frontier.claim_next_queued(r1))
                self.assertIsNotNone(repos.frontier.claim_next_queued(r2))
                self.assertEqual(repos.frontier.count_by_status(r1, "processing"), 1)
                self.assertEqual(repos.frontier.count_by_status(r2, "processing"), 1)
                moved = repos.frontier.requeue_all_stale_processing()
                self.assertEqual(moved, 2)
                self.assertEqual(repos.frontier.count_by_status(r1, "queued"), 1)
                self.assertEqual(repos.frontier.count_by_status(r2, "queued"), 1)
                self.assertEqual(repos.frontier.count_by_status(r1, "processing"), 0)
                self.assertEqual(repos.frontier.count_by_status(r2, "processing"), 0)

    def test_cross_run_same_url_allowed_two_rows(self) -> None:
        """UNIQUE is (crawl_run_id, url): same path string in different runs is OK."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                shared = "https://shared.test/article"
                r1 = repos.crawl_runs.create("https://alpha.test/", 1)
                r2 = repos.crawl_runs.create("https://beta.test/", 1)
                repos.pages.save_fetched_page(
                    r1,
                    url=shared,
                    origin_url="https://alpha.test/",
                    depth=0,
                    title=None,
                    content_text=None,
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                )
                repos.pages.save_fetched_page(
                    r2,
                    url=shared,
                    origin_url="https://beta.test/",
                    depth=0,
                    title=None,
                    content_text=None,
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                )
                n = int(
                    conn.execute(
                        "SELECT COUNT(*) AS c FROM pages WHERE url = ?",
                        (shared,),
                    ).fetchone()["c"]
                )
                self.assertEqual(n, 2)


if __name__ == "__main__":
    unittest.main()
