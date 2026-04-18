"""Repository-style accessors for crawl and search persistence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass
class CrawlRunRepository:
    conn: sqlite3.Connection

    def create(self, origin_url: str, max_depth: int) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO crawl_runs (origin_url, max_depth, status)
            VALUES (?, ?, 'active')
            """,
            (origin_url, max_depth),
        )
        return int(cur.lastrowid)

    # TODO: update status, list runs, timestamps for coordinator lifecycle.


@dataclass
class FrontierRepository:
    conn: sqlite3.Connection

    def enqueue_origin(self, crawl_run_id: int, origin_url: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO frontier (crawl_run_id, url, origin_url, depth, discovered_from, status)
            VALUES (?, ?, ?, 0, NULL, 'queued')
            """,
            (crawl_run_id, origin_url, origin_url),
        )

    # TODO: claim next queued row (queued -> processing), mark done/failed, bulk insert children with depth checks.


@dataclass
class PageRepository:
    conn: sqlite3.Connection

    def insert_placeholder(self, crawl_run_id: int, url: str, origin_url: str, depth: int) -> int:
        """Minimal row for wiring tests; full fetch fields filled by indexer/crawler later."""
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO pages (
                crawl_run_id, url, origin_url, depth, indexed_status
            ) VALUES (?, ?, ?, ?, 'not_indexed')
            """,
            (crawl_run_id, url, origin_url, depth),
        )
        if cur.lastrowid:
            return int(cur.lastrowid)
        row = self.conn.execute(
            "SELECT id FROM pages WHERE crawl_run_id = ? AND url = ?",
            (crawl_run_id, url),
        ).fetchone()
        return int(row["id"])

    # TODO: upsert after fetch (title, content_text, http_status, fetch_status, fetched_at).


@dataclass
class IndexRepository:
    conn: sqlite3.Connection

    def get_or_create_term(self, term: str) -> int:
        self.conn.execute("INSERT OR IGNORE INTO terms (term) VALUES (?)", (term,))
        row = self.conn.execute("SELECT id FROM terms WHERE term = ?", (term,)).fetchone()
        return int(row["id"])

    # TODO: upsert page_terms frequencies; mark pages indexed_status transitions.


@dataclass
class SearchRepository:
    conn: sqlite3.Connection

    def search_placeholder(self, _query: str) -> list[dict[str, Any]]:
        # TODO: tokenize query, join page_terms/terms/pages, score, return (url, origin_url, depth).
        return []


@dataclass
class Repositories:
    crawl_runs: CrawlRunRepository
    frontier: FrontierRepository
    pages: PageRepository
    index: IndexRepository
    search: SearchRepository

    @classmethod
    def from_connection(cls, conn: sqlite3.Connection) -> Repositories:
        return cls(
            crawl_runs=CrawlRunRepository(conn),
            frontier=FrontierRepository(conn),
            pages=PageRepository(conn),
            index=IndexRepository(conn),
            search=SearchRepository(conn),
        )
