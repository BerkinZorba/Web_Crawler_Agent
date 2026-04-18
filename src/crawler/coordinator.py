"""Single-threaded crawl coordinator: DB frontier, fetch, extract, store, index.

Concurrency is intentionally modest: one worker loop claims SQLite rows sequentially.
That avoids tricky locking, matches SQLite's single-writer reality, and keeps the
design easy to explain. ``max_workers`` in config is reserved for a future thread pool;
this implementation uses one logical worker.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.config import AppConfig
from src.crawler.extractor import extract_links_and_text, extract_title
from src.crawler.fetcher import fetch_page
from src.crawler.frontier import CrawlProgress, crawl_progress_snapshot, wait_for_enqueue_slot
from src.crawler.normalizer import normalize_url
from src.indexer.indexer import Indexer, PageIndexInput
from src.storage.db import open_connection
from src.storage.repositories import FrontierEntry, Repositories

log = logging.getLogger(__name__)


class CrawlCoordinator:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def run(self, origin: str, max_depth: int) -> tuple[int, CrawlProgress]:
        """
        Create a crawl run, seed the frontier at depth 0, drain queued URLs until idle.

        Before creating the run, re-queues any frontier rows still ``processing`` from an
        earlier crashed session (all crawl runs), then commits after each URL so pages and
        index rows become visible incrementally.
        """
        origin_norm = normalize_url(origin.strip())
        conn = open_connection(self._config.db_path, with_schema=True)
        try:
            repos = Repositories.from_connection(conn)
            n_recovered = repos.frontier.requeue_all_stale_processing()
            if n_recovered:
                log.warning(
                    "Re-queued %s frontier row(s) stuck in processing from a prior session",
                    n_recovered,
                )
            run_id = repos.crawl_runs.create(origin_norm, max_depth)
            repos.frontier.enqueue_origin(run_id, origin_norm)
            indexer = Indexer(repos.index)
            max_seen_depth = 0

            while True:
                entry = repos.frontier.claim_next_queued(run_id)
                if entry is None:
                    break

                max_seen_depth = max(max_seen_depth, entry.depth)
                if entry.depth > max_depth:
                    log.warning(
                        "frontier depth %s exceeds max %s; marking failed",
                        entry.depth,
                        max_depth,
                    )
                    repos.frontier.set_frontier_status(entry.id, "failed")
                    conn.commit()
                    continue

                try:
                    success = self._process_entry(
                        repos,
                        indexer,
                        run_id,
                        origin_norm,
                        max_depth,
                        entry,
                    )
                    repos.frontier.set_frontier_status(entry.id, "done" if success else "failed")
                except Exception:
                    log.exception("unhandled error processing %s", entry.url)
                    repos.frontier.set_frontier_status(entry.id, "failed")
                conn.commit()

            repos.crawl_runs.update_status(run_id, "completed")
            conn.commit()
            snap = crawl_progress_snapshot(repos, run_id)
            merged_max = max(max_seen_depth, snap.max_depth_pages)
            progress = CrawlProgress(
                crawl_run_id=snap.crawl_run_id,
                frontier_queued=snap.frontier_queued,
                frontier_processing=snap.frontier_processing,
                frontier_done=snap.frontier_done,
                frontier_failed=snap.frontier_failed,
                pages_recorded=snap.pages_recorded,
                max_depth_pages=merged_max,
            )
            return run_id, progress
        finally:
            conn.close()

    def _process_entry(
        self,
        repos: Repositories,
        indexer: Indexer,
        run_id: int,
        run_origin: str,
        max_depth: int,
        entry: FrontierEntry,
    ) -> bool:
        """Fetch one URL, persist, index on HTTP success, enqueue children. Returns success flag."""
        result = fetch_page(
            entry.url,
            timeout_sec=self._config.fetch_timeout_sec,
            user_agent=self._config.user_agent,
        )

        page_url = entry.url
        if result.fetch_status == "ok" and result.final_url:
            try:
                page_url = normalize_url(result.final_url)
            except ValueError:
                page_url = entry.url

        title = extract_title(result.body) if result.body else None
        content_text = ""
        child_links: list[str] = []
        if result.body and result.is_crawlable_html:
            child_links, content_text = extract_links_and_text(result.body, page_url)
        elif result.body and result.fetch_status == "ok":
            content_text = result.body.decode("utf-8", errors="replace")[:200_000]

        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        page_id = repos.pages.save_fetched_page(
            run_id,
            url=page_url,
            origin_url=run_origin,
            depth=entry.depth,
            title=title,
            content_text=content_text or None,
            http_status=result.status_code,
            fetch_status=result.fetch_status,
            fetched_at=fetched_at,
            indexed_status="not_indexed",
        )

        if result.fetch_status == "ok":
            indexer.index_page(
                PageIndexInput(page_id=page_id, title=title, content_text=content_text or None)
            )

        if result.fetch_status == "ok" and result.is_crawlable_html:
            child_depth = entry.depth + 1
            if child_depth <= max_depth:
                for link in child_links:
                    wait_for_enqueue_slot(
                        repos.frontier,
                        run_id,
                        self._config.queue_max_size,
                    )
                    if repos.frontier.url_known_for_run(run_id, link):
                        continue
                    repos.frontier.try_enqueue_url(
                        run_id,
                        url=link,
                        origin_url=run_origin,
                        depth=child_depth,
                        discovered_from=page_url,
                    )
        elif result.fetch_status != "ok":
            log.info("fetch not ok for %s (%s)", entry.url, result.fetch_status)

        return result.fetch_status == "ok"
