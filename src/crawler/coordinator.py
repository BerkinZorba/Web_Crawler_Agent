"""Crawl coordinator: frontier scheduling, depth limits, worker pool (TODO)."""

from __future__ import annotations

# TODO: bounded queue + worker tasks; persist frontier transitions via repositories.


class CrawlCoordinator:
    """Owns the crawl run loop and backpressure boundaries."""

    def __init__(self) -> None:
        # TODO: inject config, repositories, fetcher, extractor.
        pass

    def run(self) -> None:
        # TODO: drain frontier until empty or stopped; respect max_depth and dedup.
        raise NotImplementedError
