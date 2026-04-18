"""Repository-style accessors for crawl and search persistence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class FrontierEntry:
    """One frontier row after a successful claim."""

    id: int
    crawl_run_id: int
    url: str
    origin_url: str
    depth: int
    discovered_from: str | None


@dataclass
class CrawlRunRepository:
    conn: sqlite3.Connection

    def create(self, origin_url: str, max_depth: int, *, status: str = "active") -> int:
        cur = self.conn.execute(
            """
            INSERT INTO crawl_runs (origin_url, max_depth, status)
            VALUES (?, ?, ?)
            """,
            (origin_url, max_depth, status),
        )
        return int(cur.lastrowid)

    def update_status(self, crawl_run_id: int, status: str) -> None:
        self.conn.execute(
            """
            UPDATE crawl_runs
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, crawl_run_id),
        )

    def recent_runs(self, limit: int = 10) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT id, origin_url, max_depth, status, created_at, updated_at
                FROM crawl_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )


@dataclass
class FrontierRepository:
    conn: sqlite3.Connection

    def enqueue_origin(self, crawl_run_id: int, origin_url: str) -> bool:
        """Seed depth-0 URL for a run. Returns True if a new row was inserted."""
        return self.try_enqueue_url(
            crawl_run_id,
            url=origin_url,
            origin_url=origin_url,
            depth=0,
            discovered_from=None,
        )

    def try_enqueue_url(
        self,
        crawl_run_id: int,
        *,
        url: str,
        origin_url: str,
        depth: int,
        discovered_from: str | None,
    ) -> bool:
        """
        Insert a discovered URL into the frontier if it is not already present for this run.
        Duplicate URLs are dropped by UNIQUE (crawl_run_id, url); returns True on insert.
        """
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO frontier (
                crawl_run_id, url, origin_url, depth, discovered_from, status
            )
            VALUES (?, ?, ?, ?, ?, 'queued')
            """,
            (crawl_run_id, url, origin_url, depth, discovered_from),
        )
        return cur.rowcount > 0

    def url_known_for_run(self, crawl_run_id: int, url: str) -> bool:
        """True if the URL is already queued/processed in the frontier or stored as a page."""
        row = self.conn.execute(
            """
            SELECT 1 AS ok
            FROM frontier
            WHERE crawl_run_id = ? AND url = ?
            LIMIT 1
            """,
            (crawl_run_id, url),
        ).fetchone()
        if row is not None:
            return True
        row = self.conn.execute(
            """
            SELECT 1 AS ok
            FROM pages
            WHERE crawl_run_id = ? AND url = ?
            LIMIT 1
            """,
            (crawl_run_id, url),
        ).fetchone()
        return row is not None

    def claim_next_queued(self, crawl_run_id: int) -> FrontierEntry | None:
        """
        Atomically move the oldest queued frontier row to 'processing' and return it.
        Returns None when the queue is empty.
        """
        cur = self.conn.execute(
            """
            UPDATE frontier
            SET status = 'processing', updated_at = datetime('now')
            WHERE id = (
                SELECT id FROM frontier
                WHERE crawl_run_id = ? AND status = 'queued'
                ORDER BY id ASC
                LIMIT 1
            )
            RETURNING id, crawl_run_id, url, origin_url, depth, discovered_from
            """,
            (crawl_run_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return FrontierEntry(
            id=int(row["id"]),
            crawl_run_id=int(row["crawl_run_id"]),
            url=str(row["url"]),
            origin_url=str(row["origin_url"]),
            depth=int(row["depth"]),
            discovered_from=row["discovered_from"],
        )

    def set_frontier_status(self, frontier_id: int, status: str) -> None:
        self.conn.execute(
            """
            UPDATE frontier
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, frontier_id),
        )

    def count_by_status(self, crawl_run_id: int, status: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM frontier
            WHERE crawl_run_id = ? AND status = ?
            """,
            (crawl_run_id, status),
        ).fetchone()
        return int(row["c"])


@dataclass
class PageRepository:
    conn: sqlite3.Connection

    def insert_placeholder(self, crawl_run_id: int, url: str, origin_url: str, depth: int) -> int:
        """Insert a minimal page row if missing; returns the page primary key."""
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO pages (
                crawl_run_id, url, origin_url, depth, indexed_status
            ) VALUES (?, ?, ?, ?, 'not_indexed')
            """,
            (crawl_run_id, url, origin_url, depth),
        )
        if cur.rowcount:
            return int(cur.lastrowid)
        row = self.conn.execute(
            "SELECT id FROM pages WHERE crawl_run_id = ? AND url = ?",
            (crawl_run_id, url),
        ).fetchone()
        assert row is not None
        return int(row["id"])

    def save_fetched_page(
        self,
        crawl_run_id: int,
        *,
        url: str,
        origin_url: str,
        depth: int,
        title: str | None,
        content_text: str | None,
        http_status: int | None,
        fetch_status: str,
        fetched_at: str,
        indexed_status: str = "not_indexed",
    ) -> int:
        """
        Insert or update page content after a fetch. Preserves origin_url and depth on every write.
        """
        cur = self.conn.execute(
            """
            INSERT INTO pages (
                crawl_run_id, url, origin_url, depth,
                title, content_text, http_status, fetch_status,
                indexed_status, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (crawl_run_id, url) DO UPDATE SET
                origin_url = excluded.origin_url,
                depth = excluded.depth,
                title = excluded.title,
                content_text = excluded.content_text,
                http_status = excluded.http_status,
                fetch_status = excluded.fetch_status,
                indexed_status = excluded.indexed_status,
                fetched_at = excluded.fetched_at
            RETURNING id
            """,
            (
                crawl_run_id,
                url,
                origin_url,
                depth,
                title,
                content_text,
                http_status,
                fetch_status,
                indexed_status,
                fetched_at,
            ),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def count_for_run(self, crawl_run_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM pages WHERE crawl_run_id = ?",
            (crawl_run_id,),
        ).fetchone()
        return int(row["c"])

    def max_depth_for_run(self, crawl_run_id: int) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(depth), 0) AS m FROM pages WHERE crawl_run_id = ?",
            (crawl_run_id,),
        ).fetchone()
        return int(row["m"])


@dataclass
class IndexRepository:
    conn: sqlite3.Connection

    def get_or_create_term(self, term: str) -> int:
        normalized = term.strip().lower()
        self.conn.execute("INSERT OR IGNORE INTO terms (term) VALUES (?)", (normalized,))
        row = self.conn.execute(
            "SELECT id FROM terms WHERE term = ?",
            (normalized,),
        ).fetchone()
        assert row is not None
        return int(row["id"])

    def replace_page_terms(
        self,
        page_id: int,
        entries: Sequence[tuple[int, int, int]],
    ) -> None:
        """
        Replace all term postings for a page.
        Each entry is (term_id, frequency, in_title_frequency).
        """
        self.conn.execute("DELETE FROM page_terms WHERE page_id = ?", (page_id,))
        self.conn.executemany(
            """
            INSERT INTO page_terms (page_id, term_id, frequency, in_title_frequency)
            VALUES (?, ?, ?, ?)
            """,
            [(page_id, tid, freq, title_freq) for tid, freq, title_freq in entries],
        )

    def set_page_indexed_status(self, page_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE pages SET indexed_status = ? WHERE id = ?",
            (status, page_id),
        )


@dataclass
class SearchRepository:
    conn: sqlite3.Connection

    def resolve_term_ids(self, terms: Sequence[str]) -> list[int]:
        """Map query tokens to term ids (only terms that exist in the index)."""
        if not terms:
            return []
        lowered = list(dict.fromkeys(t.strip().lower() for t in terms if t.strip()))
        if not lowered:
            return []
        placeholders = ",".join("?" * len(lowered))
        rows = self.conn.execute(
            f"SELECT id FROM terms WHERE term IN ({placeholders})",
            lowered,
        ).fetchall()
        return [int(r["id"]) for r in rows]

    def candidate_pages_for_term_ids(
        self,
        term_ids: Sequence[int],
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Keyword OR search over indexed pages: score = sum of term frequencies.
        Returns dicts with page_id, url, origin_url, depth, score.
        """
        ids = sorted(set(term_ids))
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        sql = f"""
            SELECT
                p.id AS page_id,
                p.url AS url,
                p.origin_url AS origin_url,
                p.depth AS depth,
                SUM(pt.frequency) AS score
            FROM page_terms AS pt
            INNER JOIN pages AS p ON p.id = pt.page_id
            WHERE p.indexed_status = 'indexed'
              AND pt.term_id IN ({placeholders})
            GROUP BY p.id
            ORDER BY score DESC
            LIMIT ?
        """
        rows = self.conn.execute(sql, (*ids, limit)).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "page_id": int(r["page_id"]),
                    "url": str(r["url"]),
                    "origin_url": str(r["origin_url"]),
                    "depth": int(r["depth"]),
                    "score": int(r["score"]),
                }
            )
        return out


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
