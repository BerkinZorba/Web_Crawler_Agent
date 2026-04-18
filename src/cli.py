"""Argument parsing and command dispatch (scaffold only)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.config import AppConfig, load_config
from src.crawler.coordinator import CrawlCoordinator
from src.storage.db import connect
from src.utils.logging_utils import setup_logging

log = logging.getLogger(__name__)


def _cmd_init_db(config: AppConfig) -> None:
    with connect(config.db_path, with_schema=True):
        pass
    log.info("Database ready at %s", config.db_path)


def _cmd_index(config: AppConfig, origin: str, depth: int) -> None:
    coordinator = CrawlCoordinator(config)
    run_id, progress = coordinator.run(origin, depth)
    log.info(
        "Crawl run %s finished: queued=%s processing=%s done=%s failed=%s pages=%s max_depth=%s",
        run_id,
        progress.frontier_queued,
        progress.frontier_processing,
        progress.frontier_done,
        progress.frontier_failed,
        progress.pages_recorded,
        progress.max_depth_pages,
    )


def _cmd_search(_config: AppConfig, _query: str) -> None:
    # TODO: tokenize query, read index, print (relevant_url, origin_url, depth) rows.
    raise NotImplementedError("search will query the index; not implemented yet.")


def _cmd_status(_config: AppConfig) -> None:
    # TODO: print crawl run / frontier summary from DB.
    raise NotImplementedError("status will summarize persisted crawl state; not implemented yet.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Localhost web crawler and keyword search (scaffold).")
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to JSON config file (default: config/default.json).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create database file and apply schema.")

    ip = sub.add_parser("index", help="Start a crawl from origin URL up to depth k.")
    ip.add_argument("origin", help="Starting URL for the crawl run.")
    ip.add_argument("depth", type=int, help="Maximum crawl depth k.")

    sp = sub.add_parser("search", help="Run a keyword search over indexed pages.")
    sp.add_argument("query", help="Space-separated keywords.")

    sub.add_parser("status", help="Show crawl/index status from the database.")

    return p


def main(argv: list[str] | None = None) -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)

    if args.command == "init-db":
        _cmd_init_db(config)
    elif args.command == "index":
        _cmd_index(config, args.origin, args.depth)
    elif args.command == "search":
        _cmd_search(config, args.query)
    elif args.command == "status":
        _cmd_status(config)
    else:  # pragma: no cover
        parser.error(f"unknown command {args.command!r}")
