-- SQLite schema for localhost crawler + keyword search.
-- Matches crawl runs, frontier, pages, and inverted-index style term storage.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin_url TEXT NOT NULL,
    max_depth INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS frontier (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_run_id INTEGER NOT NULL REFERENCES crawl_runs(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    origin_url TEXT NOT NULL,
    depth INTEGER NOT NULL,
    discovered_from TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (crawl_run_id, url)
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_run_id INTEGER NOT NULL REFERENCES crawl_runs(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    origin_url TEXT NOT NULL,
    depth INTEGER NOT NULL,
    title TEXT,
    content_text TEXT,
    http_status INTEGER,
    fetch_status TEXT,
    indexed_status TEXT NOT NULL DEFAULT 'not_indexed',
    fetched_at TEXT,
    UNIQUE (crawl_run_id, url)
);

CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS page_terms (
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    term_id INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
    frequency INTEGER NOT NULL DEFAULT 0,
    in_title_frequency INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (page_id, term_id)
);

CREATE INDEX IF NOT EXISTS idx_frontier_run_status ON frontier (crawl_run_id, status);
CREATE INDEX IF NOT EXISTS idx_pages_run_url ON pages (crawl_run_id, url);
CREATE INDEX IF NOT EXISTS idx_pages_indexed ON pages (indexed_status);
CREATE INDEX IF NOT EXISTS idx_terms_term ON terms (term);
CREATE INDEX IF NOT EXISTS idx_page_terms_term ON page_terms (term_id);
