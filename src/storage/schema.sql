-- SQLite schema for localhost crawler + keyword search.
-- Tables: crawl_runs, frontier, pages, terms, page_terms

PRAGMA foreign_keys = ON;

-- One invocation of index(origin, k). status examples: active, completed, failed.
CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin_url TEXT NOT NULL,
    max_depth INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Discovered URLs to fetch. status: queued, processing, done, failed.
-- UNIQUE (crawl_run_id, url): duplicate prevention for the frontier queue.
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

-- Fetched documents. origin_url and depth come from the frontier row that was processed.
-- UNIQUE (crawl_run_id, url): one stored page per normalized URL per run.
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

-- Frontier: pick next queued row by run; filter by status.
CREATE INDEX IF NOT EXISTS idx_frontier_run_status_id ON frontier (crawl_run_id, status, id);

-- Faster “claim next” for large queues (SQLite partial index).
CREATE INDEX IF NOT EXISTS idx_frontier_run_queued_id ON frontier (crawl_run_id, id)
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_pages_run_url ON pages (crawl_run_id, url);
CREATE INDEX IF NOT EXISTS idx_pages_indexed ON pages (indexed_status);
CREATE INDEX IF NOT EXISTS idx_pages_run_indexed ON pages (crawl_run_id, indexed_status);

CREATE INDEX IF NOT EXISTS idx_terms_term ON terms (term);

-- Inverted index lookups: term_id -> pages; page_id -> terms (for replacements).
CREATE INDEX IF NOT EXISTS idx_page_terms_term ON page_terms (term_id);
CREATE INDEX IF NOT EXISTS idx_page_terms_page ON page_terms (page_id);
