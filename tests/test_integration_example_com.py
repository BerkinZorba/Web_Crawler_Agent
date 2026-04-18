"""Live integration smoke test against https://example.com/ (IANA documentation host)."""

from __future__ import annotations

import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from src.config import AppConfig
from src.crawler.coordinator import CrawlCoordinator
from src.search.engine import SearchEngine
from src.storage.db import connect
from src.storage.repositories import Repositories


def _example_com_reachable() -> bool:
    try:
        with urllib.request.urlopen("https://example.com/", timeout=15) as resp:
            code = resp.getcode()
            return 200 <= int(code) < 400
    except (OSError, urllib.error.HTTPError, urllib.error.URLError):
        return False


@unittest.skipUnless(
    _example_com_reachable(),
    "https://example.com/ not reachable (offline or blocked); skipping live integration test",
)
class ExampleComIntegrationTests(unittest.TestCase):
    def test_crawl_index_search_example_com(self) -> None:
        """Depth-1 crawl stores pages (with indexing in the coordinator), search finds 'example'."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "integration.db"
            cfg = AppConfig(
                db_path=db_path,
                max_workers=1,
                fetch_timeout_sec=20.0,
                queue_max_size=500,
                user_agent="WebCrawlerAgent-IntegrationTest/1.0",
            )
            run_id, _ = CrawlCoordinator(cfg).run("https://example.com/", max_depth=1)

            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                stored = repos.pages.count_for_run(run_id)
                self.assertGreaterEqual(
                    stored,
                    1,
                    "expected at least the seed page to be stored",
                )
                indexed = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM pages
                    WHERE crawl_run_id = ? AND indexed_status = 'indexed'
                    """,
                    (run_id,),
                ).fetchone()
                self.assertGreaterEqual(
                    int(indexed["c"]),
                    1,
                    "coordinator should index successful fetches",
                )
                results = SearchEngine(repos.search).search("example")
                self.assertGreaterEqual(
                    len(results),
                    1,
                    "expected keyword 'example' to match example.com body/title tokens",
                )


if __name__ == "__main__":
    unittest.main()
