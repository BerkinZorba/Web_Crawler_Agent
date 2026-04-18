"""CLI: init-db, index, search, status, resume — localhost demo interface."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from textwrap import dedent

from src.config import AppConfig, load_config
from src.crawler.coordinator import CrawlCoordinator
from src.crawler.frontier import crawl_progress_snapshot
from src.search.engine import SearchEngine
from src.storage.db import connect
from src.storage.repositories import Repositories
from src.utils.logging_utils import setup_logging

log = logging.getLogger(__name__)

_EPILOG = dedent(
    """
    Examples:
      python -m src.main init-db
      python -m src.main index --origin https://example.com/ --depth 1
      python -m src.main search --query "python crawler"
      python -m src.main status
      python -m src.main resume
    """
).strip()


def _cmd_init_db(config: AppConfig) -> None:
    with connect(config.db_path, with_schema=True):
        pass
    print(f"Database ready: {config.db_path}")
    log.info("Database ready at %s", config.db_path)


def _cmd_index(config: AppConfig, origin: str, depth: int) -> None:
    print(f"Starting crawl: origin={origin!r}  max_depth={depth}")
    print(f"Database: {config.db_path}")
    coordinator = CrawlCoordinator(config)
    run_id, progress = coordinator.run(origin, depth)
    print()
    print("Crawl finished")
    print(f"  run_id:          {run_id}")
    print(f"  frontier queued: {progress.frontier_queued}")
    print(f"  frontier done:   {progress.frontier_done}")
    print(f"  frontier failed: {progress.frontier_failed}")
    print(f"  pages stored:    {progress.pages_recorded}")
    print(f"  max depth seen:  {progress.max_depth_pages}")
    log.info(
        "Crawl run %s: queued=%s done=%s failed=%s pages=%s max_depth=%s",
        run_id,
        progress.frontier_queued,
        progress.frontier_done,
        progress.frontier_failed,
        progress.pages_recorded,
        progress.max_depth_pages,
    )


def _cmd_search(config: AppConfig, query: str) -> None:
    results: list[tuple[str, str, int]] = []
    try:
        with connect(config.db_path, with_schema=True) as conn:
            repos = Repositories.from_connection(conn)
            engine = SearchEngine(repos.search)
            results = engine.search(query)
    except Exception:
        log.warning("search: command failed (database or unexpected error)", exc_info=True)
        results = []

    if not results:
        print("No indexed pages matched your query.")
        print("(Pages must be crawled and indexed; very common words may be ignored.)")
        return

    print(f"Results ({len(results)}):")
    print()
    w_url = max(len(r[0]) for r in results)
    w_origin = max(len(r[1]) for r in results)
    header = f"  {'relevant_url'.ljust(w_url)}  {'origin_url'.ljust(w_origin)}  depth"
    print(header)
    print(f"  {'-' * len(header)}")
    for url, origin_url, depth in results:
        print(f"  {url.ljust(w_url)}  {origin_url.ljust(w_origin)}  {depth}")


def _cmd_resume(config: AppConfig) -> None:
    with connect(config.db_path, with_schema=True) as conn:
        repos = Repositories.from_connection(conn)
        n = repos.frontier.requeue_all_stale_processing()
        conn.commit()
    print(f"Recovered {n} frontier row(s): processing → queued")
    log.info("resume: requeued %s stale processing frontier rows", n)


def _cmd_status(config: AppConfig) -> None:
    with connect(config.db_path, with_schema=True) as conn:
        repos = Repositories.from_connection(conn)
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN indexed_status = 'indexed' THEN 1 ELSE 0 END) AS indexed
            FROM pages
            """
        ).fetchone()
        total_pages = int(row["total"] or 0)
        indexed_pages = int(row["indexed"] or 0)

        print(f"Database: {config.db_path}")
        print()
        print("Pages")
        print(f"  stored:   {total_pages}")
        print(f"  indexed:  {indexed_pages} (search uses these)")
        print()
        runs = repos.crawl_runs.recent_runs(limit=8)
        if not runs:
            print("Crawl runs: none yet (use `index`).")
            return

        print("Recent crawl runs")
        print(f"  {'id':>4}  {'depth':>5}  {'status':<12}  origin")
        print("  " + "-" * 72)
        for r in runs:
            rid = int(r["id"])
            prog = crawl_progress_snapshot(repos, rid)
            origin = str(r["origin_url"])
            if len(origin) > 44:
                origin = origin[:41] + "..."
            print(
                f"  {rid:>4}  {int(r['max_depth']):>5}  {str(r['status']):<12}  {origin}"
            )
            print(
                f"        queued={prog.frontier_queued}  done={prog.frontier_done}  "
                f"failed={prog.frontier_failed}  pages={prog.pages_recorded}"
            )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.main",
        description=(
            "Localhost web crawler and keyword search: SQLite storage, incremental index, "
            "simple CLI for demos."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="JSON config file (default: config/default.json under the project).",
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    sub.add_parser("init-db", help="Create or open the DB file and apply schema if needed.")

    ip = sub.add_parser(
        "index",
        help="Run a crawl from --origin up to hop depth --depth (persists pages and index).",
    )
    ip.add_argument(
        "--origin",
        required=True,
        metavar="URL",
        help="Starting URL (http or https), e.g. https://example.com/",
    )
    ip.add_argument(
        "--depth",
        type=int,
        required=True,
        metavar="K",
        help="Maximum crawl depth: 0 = seed only, 1 = seed + its links, etc.",
    )

    sp = sub.add_parser(
        "search",
        help="Keyword search over pages marked indexed (same token rules as indexing).",
    )
    sp.add_argument(
        "--query",
        required=True,
        metavar="TEXT",
        help='Search text, e.g. "python tutorial".',
    )

    sub.add_parser(
        "status",
        help="Show DB path, page/index counts, and recent crawl runs with frontier stats.",
    )

    sub.add_parser(
        "resume",
        help="Re-queue frontier rows stuck in processing (e.g. after a crash).",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)

    try:
        if args.command == "init-db":
            _cmd_init_db(config)
        elif args.command == "index":
            _cmd_index(config, args.origin, args.depth)
        elif args.command == "search":
            _cmd_search(config, args.query)
        elif args.command == "status":
            _cmd_status(config)
        elif args.command == "resume":
            _cmd_resume(config)
        else:  # pragma: no cover
            parser.error(f"unknown command {args.command!r}")
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        log.exception("Command failed")
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
