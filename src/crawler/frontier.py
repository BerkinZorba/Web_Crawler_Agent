"""Frontier helpers: in-memory test queue, crawl progress snapshot, enqueue backpressure."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from src.storage.repositories import FrontierRepository, Repositories


@dataclass(frozen=True)
class FrontierTask:
    url: str
    origin_url: str
    depth: int
    discovered_from: str | None


@dataclass(frozen=True)
class CrawlProgress:
    """Point-in-time stats for monitoring (mostly derived from SQLite)."""

    crawl_run_id: int
    frontier_queued: int
    frontier_processing: int
    frontier_done: int
    frontier_failed: int
    pages_recorded: int
    max_depth_pages: int


class InMemoryFrontier:
    """Optional helper for tests; production crawling uses persisted ``frontier`` rows."""

    def __init__(self) -> None:
        self._q: deque[FrontierTask] = deque()

    def push(self, task: FrontierTask) -> None:
        self._q.append(task)

    def pop(self) -> FrontierTask | None:
        if not self._q:
            return None
        return self._q.popleft()


def wait_for_enqueue_slot(
    frontier: FrontierRepository,
    crawl_run_id: int,
    queue_max_size: int,
    *,
    poll_sec: float = 0.05,
) -> None:
    """
    Block until the persisted ``queued`` count is below ``queue_max_size``.

    This is the backpressure valve: producers (link discovery) pause when the DB
    frontier is full so memory and SQLite work stay bounded.
    """
    cap = max(1, queue_max_size)
    while frontier.count_by_status(crawl_run_id, "queued") >= cap:
        time.sleep(poll_sec)


def crawl_progress_snapshot(repos: Repositories, crawl_run_id: int) -> CrawlProgress:
    """Read counts from storage for status UIs or logging."""
    fr = repos.frontier
    pg = repos.pages
    return CrawlProgress(
        crawl_run_id=crawl_run_id,
        frontier_queued=fr.count_by_status(crawl_run_id, "queued"),
        frontier_processing=fr.count_by_status(crawl_run_id, "processing"),
        frontier_done=fr.count_by_status(crawl_run_id, "done"),
        frontier_failed=fr.count_by_status(crawl_run_id, "failed"),
        pages_recorded=pg.count_for_run(crawl_run_id),
        max_depth_pages=pg.max_depth_for_run(crawl_run_id),
    )
