"""Smoke tests for SQLite bootstrap and repository wiring."""

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
                repos.frontier.enqueue_origin(run_id, "https://example.com/")
                page_id = repos.pages.insert_placeholder(
                    run_id, "https://example.com/", "https://example.com/", 0
                )
                term_id = repos.index.get_or_create_term("hello")
                self.assertGreater(run_id, 0)
                self.assertGreater(page_id, 0)
                self.assertGreater(term_id, 0)


if __name__ == "__main__":
    unittest.main()
