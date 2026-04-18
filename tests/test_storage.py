"""Tests for SQLite bootstrap and repository behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.storage.db import connect
from src.storage.repositories import Repositories


class StorageTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
