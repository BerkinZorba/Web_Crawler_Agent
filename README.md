# Web Crawler Agent — Localhost Crawler & Search

## 1. Project overview

This is an **educational, localhost-only** Python application that combines:

- A **depth-limited web crawler** that starts from one origin URL, follows links in fetched HTML, and stores pages in a local **SQLite** database.
- A **keyword search engine** over those pages, returning each hit as **`(relevant_url, origin_url, depth)`** — the URL of the page, the crawl’s seed URL, and the hop depth from that seed.

**Scope:** single machine, no production deployment story, no distributed crawl. It is meant for coursework, demos, and small test sites you are allowed to fetch. Do not point it at sites you do not own or lack permission to crawl.

The assignment’s “multi-agent” aspect is documented in **`docs/multi_agent_workflow.md`**: roles were used **during development**, not as runtime AI agents inside the program.

---

## 2. How to run

### Python version

- **Python 3.11+** (see `requirements.txt`).

### Install

There are **no mandatory third-party packages** at runtime; the crawler uses the standard library (`urllib`, `html.parser`, `sqlite3`, etc.).

```bash
cd /path/to/Web_Crawler_Agent
# optional: python3 -m venv .venv && source .venv/bin/activate
```

If you add dev tools later, use `pip install -r requirements.txt` (file is mostly comments today).

### Configuration

Defaults live in **`config/default.json`** (e.g. database path `data/crawler.db`, fetch timeout, **`queue_max_size`** for backpressure, `User-Agent`). Override with:

```bash
python3 -m src.main --config /path/to/custom.json COMMAND ...
```

Paths in the config are resolved relative to the project root when relative.

### Commands

Run from the **project root** so `src` is importable as a package.

| Command | Purpose |
|--------|---------|
| **init-db** | Create/open the SQLite file and apply the schema if needed. |
| **index** | Run one **crawl run**: `--origin` URL and `--depth` *k* (max hop depth). |
| **search** | Keyword search over **indexed** pages only: `--query "..."`. |
| **status** | Print DB path, page/index counts, and recent crawl runs + frontier stats. |
| **resume** | Re-queue frontier rows stuck in **`processing`** (e.g. after a crash). See §7. |

```bash
python3 -m src.main --help
python3 -m src.main init-db
python3 -m src.main index --origin https://example.com/ --depth 1
python3 -m src.main search --query "documentation"
python3 -m src.main status
python3 -m src.main resume
```

---

## 3. Example usage (typical sequence)

Use only hosts you are allowed to access. Example with a small public site:

```bash
# 1) Create database and tables
python3 -m src.main init-db

# 2) Crawl from a seed URL up to depth 1 (seed + its direct links)
python3 -m src.main index --origin https://example.com/ --depth 1

# 3) Search indexed text (tokens must exist in the index; stopwords are dropped)
python3 -m src.main search --query "example"

# 4) Inspect stored state
python3 -m src.main status
```

Expected flow: **`init-db`** prints the DB path → **`index`** prints run id and frontier/page summary → **`search`** prints a table of **`relevant_url`**, **`origin_url`**, **`depth`** (or a message if nothing matched) → **`status`** shows global counts and recent runs.

---

## 4. Architecture summary (short)

| Layer | Role |
|-------|------|
| **Crawler** | `src/crawler/coordinator.py` drives a **persisted frontier** in SQLite: claim URL → `fetcher` → save page → `indexer` on success → extract links from HTML → enqueue children within depth and queue limits. Normalization and extraction: `normalizer.py`, `extractor.py`. |
| **Storage** | `src/storage/schema.sql` + `db.py` + `repositories.py`: crawl runs, frontier rows, pages, terms, `page_terms` (inverted index style). WAL and short transactions support incremental visibility. |
| **Indexer** | `src/indexer/indexer.py` tokenizes title/body (same rules as search), writes term frequencies, sets **`indexed_status`** to **`indexed`** when done (or **`index_failed`** on error). |
| **Search** | `src/search/engine.py` resolves query tokens to term ids, loads candidate pages that are **`indexed`**, scores them with **`src/indexer/ranking.py`**, returns ordered **`(url, origin_url, depth)`** triples. |

---

## 5. Backpressure (how it actually works)

The crawler does not hold an unbounded list of discovered URLs in memory for enqueue. Before each new frontier insert, it calls **`wait_for_enqueue_slot`** (`src/crawler/frontier.py`): if the number of **`queued`** rows for the current crawl run is **≥ `queue_max_size`** (from config), it **sleeps and retries** until the count drops below the cap (normally because URLs are claimed and eventually marked **done** or **failed**).

So backpressure is **persisted queue depth + polling**, not a separate in-memory broker.

**Single worker model:** the coordinator runs **one sequential loop** (one logical worker). `max_workers` in config is reserved for a possible future thread pool; today crawl throughput is intentionally simple and SQLite-friendly.

---

## 6. Search while indexing (eventual consistency)

- Pages are committed **after each fetched URL**; the indexer runs in the same flow for successful HTTP responses.
- Search queries only **`pages.indexed_status = 'indexed'`**. Rows in **`indexing`**, **`not_indexed`**, or **`index_failed`** do not appear in results.
- So during a long crawl, **search sees a growing subset** of pages: **eventual consistency** — results improve as more pages finish indexing; you never get partial token rows for a page that is still mid-index in a way that search would expose (the indexer moves through **`indexing`** to **`indexed`** or **`index_failed`**).

---

## 7. Resume behavior (partial)

The system provides **partial** resume support for stuck frontier state, not full “continue where I left off” crawling.

- **CLI `resume`:** moves **every** frontier row in **`processing`** back to **`queued`** (all crawl runs), and prints how many rows were recovered. Use this after a crash so those URLs can be claimed again **if** something drains that run’s frontier.
- **Automatic cleanup on new crawl:** `CrawlCoordinator` calls the same global requeue logic **before** creating a new run when you run **`index`**, so stale **`processing`** rows from an earlier session are not left orphaned.

**Limitations:**

- The system does **not** fully continue a **previous** crawl run: there is no `index --continue-run-id`.
- Each **`index`** creates a **new** `crawl_run_id`; it does not drain remaining **`queued`** URLs from an interrupted older run.
- **`resume`** repairs **processing → queued**; it does not by itself finish an old run’s queue.

This keeps behavior predictable for a localhost, educational build.

---

## 8. Known limitations (read before demo or grading)

- **Single-threaded crawl:** one URL is processed at a time in the coordinator loop; no parallel fetch pool.
- **No `robots.txt` enforcement** and no politeness policy beyond timeout, body size cap, and your own judgment about targets.
- **Limited URL normalization** (`src/crawler/normalizer.py`): ASCII-oriented token-style rules; **http vs https**, trailing-slash variants, and **redirect targets treated as new URLs** can produce **duplicate or near-duplicate pages** in the DB for what humans consider one resource.
- **No `<base href>` handling** in HTML; relative links are resolved against the fetched URL only.
- **No JavaScript rendering**; only raw HTML is parsed.
- **Fetcher body size cap** (see `fetcher.py`) — very large documents are truncated.
- **Search candidate cap** before ranking (see `indexed_candidate_stats_for_term_ids` in `repositories.py`) — huge indexes may not evaluate every matching page.

---

## 9. Ranking logic

Relevance scoring is **explicit and code-documented** in:

**`src/indexer/ranking.py`**

The search layer aggregates per-page term hits from SQLite, then applies `score_page(...)` (coverage of distinct query terms, body frequency, title frequency, small depth penalty). Weights are constants at the top of that file.

---

## Tests

```bash
python3 -m unittest discover -s tests -v
```

---

## Further reading

- **`docs/multi_agent_workflow.md`** — how documentation/architecture agents were used in development.
