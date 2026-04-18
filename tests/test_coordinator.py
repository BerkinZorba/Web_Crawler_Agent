"""Coordinator tests with mocked HTTP (no network)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config import AppConfig
from src.crawler.coordinator import CrawlCoordinator
from src.crawler.fetcher import FetchResult
from src.storage.db import open_connection
from src.storage.repositories import Repositories


def _ok_html(body: bytes) -> FetchResult:
    return FetchResult(
        requested_url="",
        final_url=None,
        status_code=200,
        content_type="text/html; charset=utf-8",
        media_type="text/html",
        body=body,
        fetch_status="ok",
        error_message=None,
    )


class CoordinatorTests(unittest.TestCase):
    @patch("src.crawler.coordinator.fetch_page")
    def test_depth_limited_enqueue(self, mock_fetch: MagicMock) -> None:
        root_html = b"""<!doctype html><html><body>
        <a href="/one">one</a>
        </body></html>"""
        leaf_html = b"<!doctype html><html><body><p>leaf</p></body></html>"

        def fetch_side_effect(url: str, **kwargs: object) -> FetchResult:
            if url.rstrip("/").endswith("example.com") or url.endswith("example.com/"):
                return _ok_html(root_html)
            if "/one" in url:
                return _ok_html(leaf_html)
            return FetchResult(
                requested_url=url,
                final_url=None,
                status_code=None,
                content_type=None,
                media_type=None,
                body=b"",
                fetch_status="network_error",
                error_message="unexpected",
            )

        mock_fetch.side_effect = fetch_side_effect

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "crawl.db"
            cfg = AppConfig(
                db_path=db_path,
                max_workers=1,
                fetch_timeout_sec=5.0,
                queue_max_size=100,
                user_agent="TestCrawler/1",
            )
            coord = CrawlCoordinator(cfg)
            run_id, progress = coord.run("https://example.com/", max_depth=1)

            self.assertGreater(run_id, 0)
            conn = open_connection(db_path, with_schema=True)
            try:
                repos = Repositories.from_connection(conn)
                dmax = repos.pages.max_depth_for_run(run_id)
                self.assertLessEqual(dmax, 1)
                n_pages = repos.pages.count_for_run(run_id)
                self.assertGreaterEqual(n_pages, 2)
                failed = repos.frontier.count_by_status(run_id, "failed")
                self.assertEqual(failed, 0)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
