"""SQLite connection helpers: WAL, schema bootstrap, short transactions."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

_SCHEMA_REL = Path(__file__).resolve().parent / "schema.sql"


def _connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def apply_schema(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    path = schema_path or _SCHEMA_REL
    conn.executescript(path.read_text(encoding="utf-8"))


def open_connection(db_path: Path, *, with_schema: bool = True) -> sqlite3.Connection:
    """
    Open a SQLite connection without wrapping a transaction.
    Caller commits explicitly (e.g. after each crawled URL) for incremental visibility.
    """
    conn = _connection(db_path)
    if with_schema:
        ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    """Apply `schema.sql` once when the database has not been initialized yet."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'crawl_runs' LIMIT 1"
    ).fetchone()
    if row is None:
        apply_schema(conn, schema_path)


@contextmanager
def connect(db_path: Path, *, with_schema: bool = True) -> Generator[sqlite3.Connection, None, None]:
    conn = _connection(db_path)
    try:
        if with_schema:
            ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
