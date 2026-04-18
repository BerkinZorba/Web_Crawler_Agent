"""Indexer: token persistence and indexed_status."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.indexer.indexer import Indexer, PageIndexInput
from src.storage.db import connect
from src.storage.repositories import Repositories


class IndexerTests(unittest.TestCase):
    def test_index_page_marks_indexed_and_stores_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "t.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://example.com/", 2)
                pid = repos.pages.save_fetched_page(
                    run_id,
                    url="https://example.com/p",
                    origin_url="https://example.com/",
                    depth=1,
                    title="Hello Python World",
                    content_text="Python is fun. Hello again.",
                    http_status=200,
                    fetch_status="ok",
                    fetched_at="2026-01-01 00:00:00",
                    indexed_status="not_indexed",
                )
                indexer = Indexer(repos.index)
                ok = indexer.index_page(
                    PageIndexInput(
                        page_id=pid,
                        title="Hello Python World",
                        content_text="Python is fun. Hello again.",
                    )
                )
                self.assertTrue(ok)

                row = conn.execute(
                    "SELECT indexed_status FROM pages WHERE id = ?",
                    (pid,),
                ).fetchone()
                self.assertEqual(row["indexed_status"], "indexed")

                n_terms = conn.execute(
                    "SELECT COUNT(*) AS c FROM page_terms WHERE page_id = ?",
                    (pid,),
                ).fetchone()["c"]
                self.assertGreater(int(n_terms), 0)

    def test_index_page_sets_failed_on_bad_page_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "t.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                indexer = Indexer(repos.index)
                ok = indexer.index_page(
                    PageIndexInput(
                        page_id=99999,
                        title="hello",
                        content_text="hello world",
                    )
                )
                self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
