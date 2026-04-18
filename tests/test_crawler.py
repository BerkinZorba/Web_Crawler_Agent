"""Crawler: normalization, extraction, in-memory frontier, coordinator (mocked HTTP)."""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config import AppConfig
from src.crawler.coordinator import CrawlCoordinator
from src.crawler.extractor import extract_links_and_text
from src.crawler.fetcher import FetchResult
from src.crawler.frontier import FrontierTask, InMemoryFrontier, wait_for_enqueue_slot
from src.crawler.normalizer import normalize_url, normalize_url_or_none, resolve_link
from src.storage.db import connect, open_connection
from src.storage.repositories import CrawlRunRepository, Repositories


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


class CrawlerTests(unittest.TestCase):
    def test_frontier_push_pop(self) -> None:
        f = InMemoryFrontier()
        f.push(FrontierTask("https://a.test/", "https://origin.test/", 0, None))
        t = f.pop()
        self.assertIsNotNone(t)
        assert t is not None
        self.assertEqual(t.url, "https://a.test/")

    def test_normalize_lowercase_host_and_strip_fragment(self) -> None:
        self.assertEqual(
            normalize_url("http://Example.COM:80/a#frag"),
            "http://example.com/a",
        )
        self.assertEqual(
            normalize_url("https://Example.COM:443/b?x=1#y"),
            "https://example.com/b?x=1",
        )

    def test_normalize_path_dots(self) -> None:
        self.assertEqual(normalize_url("http://example.com/a/./b/../c"), "http://example.com/a/c")
        self.assertEqual(normalize_url("http://example.com/a/../c"), "http://example.com/c")

    def test_normalize_rejects_schemes(self) -> None:
        for bad in ("mailto:a@b.com", "javascript:void(0)", "tel:+1"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    normalize_url(bad)

    def test_normalize_or_none_relative(self) -> None:
        base = "https://example.com/dir/page.html"
        self.assertEqual(
            normalize_url_or_none("../other", base_url=base),
            "https://example.com/other",
        )
        self.assertIsNone(normalize_url_or_none("mailto:x@y", base_url=base))

    def test_resolve_link_protocol_relative(self) -> None:
        base = "https://example.com/dir/page"
        self.assertEqual(resolve_link("//cdn.test/x", base), "https://cdn.test/x")

    def test_extract_links_dedup_and_text(self) -> None:
        html = b"""<!doctype html>
        <html><head><title>t</title></head><body>
        <a href="/a">1</a>
        <a href='/a'>dup</a>
        <a href="mailto:x@y">m</a>
        <a href="javascript:void(0)">j</a>
        <script>alert('no')</script>
        <p>Hello <b>world</b></p>
        </body></html>
        """
        base = "https://site.example/dir/page.html"
        links, text = extract_links_and_text(html, base)
        self.assertEqual(links, ["https://site.example/a"])
        self.assertIn("Hello", text)
        self.assertIn("world", text)
        self.assertNotIn("alert", text)


class CrawlCoordinatorTests(unittest.TestCase):
    @patch("src.crawler.coordinator.fetch_page")
    def test_crawl_start_requeues_stale_processing_from_prior_runs(
        self, mock_fetch: MagicMock
    ) -> None:
        """Interrupted prior run leaves processing; a new index run clears it before creating its run."""
        mock_fetch.return_value = _ok_html(b"<html><body>seed</body></html>")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "c.db"
            with connect(db_path, with_schema=True) as conn:
                repos = Repositories.from_connection(conn)
                run_old = repos.crawl_runs.create("https://prior.test/", 1)
                repos.frontier.enqueue_origin(run_old, "https://prior.test/")
                self.assertIsNotNone(repos.frontier.claim_next_queued(run_old))
                self.assertEqual(repos.frontier.count_by_status(run_old, "processing"), 1)

            cfg = AppConfig(
                db_path=db_path,
                max_workers=1,
                fetch_timeout_sec=5.0,
                queue_max_size=100,
                user_agent="TestCrawler/1",
            )
            new_run_id, _ = CrawlCoordinator(cfg).run("https://example.com/", max_depth=0)
            self.assertNotEqual(new_run_id, run_old)

            conn = open_connection(db_path, with_schema=True)
            try:
                repos = Repositories.from_connection(conn)
                self.assertEqual(repos.frontier.count_by_status(run_old, "processing"), 0)
                self.assertEqual(repos.frontier.count_by_status(run_old, "queued"), 1)
            finally:
                conn.close()

    @patch("src.crawler.coordinator.fetch_page")
    def test_crawl_run_status_failed_on_coordinator_error(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = _ok_html(b"<html><body>x</body></html>")
        orig_update = CrawlRunRepository.update_status

        def bust(self: CrawlRunRepository, crawl_run_id: int, status: str) -> None:
            if status == "completed":
                raise RuntimeError("simulated completion failure")
            orig_update(self, crawl_run_id, status)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "c.db"
            cfg = AppConfig(
                db_path=db_path,
                max_workers=1,
                fetch_timeout_sec=5.0,
                queue_max_size=100,
                user_agent="TestCrawler/1",
            )
            with patch.object(CrawlRunRepository, "update_status", bust):
                with self.assertRaises(RuntimeError):
                    CrawlCoordinator(cfg).run("https://example.com/", max_depth=0)
            conn = open_connection(db_path, with_schema=True)
            try:
                row = conn.execute(
                    "SELECT status FROM crawl_runs ORDER BY id DESC LIMIT 1"
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(str(row["status"]), "failed")
            finally:
                conn.close()

    @patch("src.crawler.coordinator.fetch_page")
    def test_crawl_run_status_interrupted_on_keyboard_interrupt(
        self, mock_fetch: MagicMock
    ) -> None:
        mock_fetch.side_effect = KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "c.db"
            cfg = AppConfig(
                db_path=db_path,
                max_workers=1,
                fetch_timeout_sec=5.0,
                queue_max_size=100,
                user_agent="TestCrawler/1",
            )
            with self.assertRaises(KeyboardInterrupt):
                CrawlCoordinator(cfg).run("https://example.com/", max_depth=0)
            conn = open_connection(db_path, with_schema=True)
            try:
                row = conn.execute(
                    "SELECT status FROM crawl_runs ORDER BY id DESC LIMIT 1"
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(str(row["status"]), "interrupted")
            finally:
                conn.close()

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
                self.assertGreater(progress.frontier_done, 0)
            finally:
                conn.close()

    @patch("src.crawler.coordinator.fetch_page")
    def test_origin_page_stored_at_depth_zero(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = _ok_html(b"<html><body>seed</body></html>")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "c.db"
            cfg = AppConfig(
                db_path=db_path,
                max_workers=1,
                fetch_timeout_sec=5.0,
                queue_max_size=100,
                user_agent="TestCrawler/1",
            )
            origin = "https://example.com/"
            run_id, _ = CrawlCoordinator(cfg).run(origin, max_depth=1)
            conn = open_connection(db_path, with_schema=True)
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM pages WHERE crawl_run_id = ? AND depth = 0",
                    (run_id,),
                ).fetchone()
                self.assertGreaterEqual(int(row["c"]), 1)
            finally:
                conn.close()

    @patch("src.crawler.coordinator.fetch_page")
    def test_max_depth_zero_skips_child_links(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = _ok_html(
            b'<html><body><a href="/child">c</a></body></html>'
        )
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "c.db"
            cfg = AppConfig(
                db_path=db_path,
                max_workers=1,
                fetch_timeout_sec=5.0,
                queue_max_size=100,
                user_agent="TestCrawler/1",
            )
            run_id, _ = CrawlCoordinator(cfg).run("https://example.com/", max_depth=0)
            conn = open_connection(db_path, with_schema=True)
            try:
                repos = Repositories.from_connection(conn)
                self.assertEqual(repos.pages.count_for_run(run_id), 1)
                self.assertEqual(repos.pages.max_depth_for_run(run_id), 0)
            finally:
                conn.close()

    @patch("src.crawler.coordinator.fetch_page")
    def test_fetch_failure_does_not_abort_crawl(self, mock_fetch: MagicMock) -> None:
        root = b"""<!doctype html><html><body>
        <a href="/bad">bad</a><a href="/ok">ok</a>
        </body></html>"""
        ok_leaf = b"<!doctype html><html><body>ok</body></html>"

        def fetch_side_effect(url: str, **kwargs: object) -> FetchResult:
            if url.rstrip("/").endswith("example.com") or url.endswith("example.com/"):
                return _ok_html(root)
            if "/bad" in url:
                return FetchResult(
                    requested_url=url,
                    final_url=None,
                    status_code=None,
                    content_type=None,
                    media_type=None,
                    body=b"",
                    fetch_status="network_error",
                    error_message="boom",
                )
            if "/ok" in url:
                return _ok_html(ok_leaf)
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
            db_path = Path(tmp) / "c.db"
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
                failed = repos.frontier.count_by_status(run_id, "failed")
                done = repos.frontier.count_by_status(run_id, "done")
                self.assertGreaterEqual(failed, 1)
                self.assertGreaterEqual(done, 1)
                self.assertGreaterEqual(repos.pages.count_for_run(run_id), 2)
            finally:
                conn.close()

    def test_backpressure_blocks_until_queued_drops_below_cap(self) -> None:
        """When queued count == cap, wait_for_enqueue_slot blocks until another conn drains one row."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "bp.db"
            conn = open_connection(db_path, with_schema=True)
            try:
                repos = Repositories.from_connection(conn)
                run_id = repos.crawl_runs.create("https://bp.test/", 2)
                cap = 3
                for i in range(cap):
                    repos.frontier.try_enqueue_url(
                        run_id,
                        url=f"https://bp.test/item{i}",
                        origin_url="https://bp.test/",
                        depth=0,
                        discovered_from=None,
                    )
                conn.commit()
                self.assertEqual(repos.frontier.count_by_status(run_id, "queued"), cap)

                def move_one_queued_to_done() -> None:
                    time.sleep(0.08)
                    c2 = sqlite3.connect(str(db_path))
                    try:
                        c2.execute("PRAGMA foreign_keys = ON")
                        c2.execute(
                            """
                            UPDATE frontier SET status = 'done', updated_at = datetime('now')
                            WHERE id = (
                                SELECT id FROM frontier
                                WHERE crawl_run_id = ? AND status = 'queued'
                                ORDER BY id LIMIT 1
                            )
                            """,
                            (run_id,),
                        )
                        c2.commit()
                    finally:
                        c2.close()

                worker = threading.Thread(target=move_one_queued_to_done)
                worker.start()
                start = time.time()
                wait_for_enqueue_slot(repos.frontier, run_id, cap, poll_sec=0.02)
                elapsed = time.time() - start
                worker.join(timeout=2.0)
                self.assertFalse(worker.is_alive())
                self.assertGreater(
                    elapsed,
                    0.04,
                    "backpressure should spin until queued count falls below cap",
                )
                self.assertLess(repos.frontier.count_by_status(run_id, "queued"), cap)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
