# Product Requirements Document — Web Crawler Agent

This document describes the **delivered** localhost crawler and keyword search system. It is aligned with the code under `src/`, not with an aspirational design. The Architect Agent’s blueprint (`agents/agent_architect.md`) guided scope; the **multi-agent workflow** was a **development process** only (`docs/multi_agent_workflow.md`), not a runtime architecture.

---

## 1. Objective

Build a **single-machine**, **educational** Python application that:

1. **Indexes** the web in a controlled way: given an **origin URL** and maximum **depth** *k*, discovers and fetches pages, persists crawl state, and builds a **keyword index** over fetched HTML/text.
2. **Searches** that index and returns each hit as **`(relevant_url, origin_url, depth)`** — the page URL, the crawl run’s seed URL, and the hop depth from that seed.

The system must remain **explainable** and **stdlib-oriented** (no full crawler or search framework replacing core logic).

---

## 2. Functional requirements

### 2.1 Index (`index`)

| ID | Requirement | Implementation notes |
|----|-------------|----------------------|
| I1 | User supplies **origin URL** and integer **max depth** *k*. | CLI: `python3 -m src.main index --origin URL --depth K`. |
| I2 | System creates a **crawl run** and seeds the **frontier** at depth **0** with the normalized origin. | `CrawlCoordinator.run` → `crawl_runs.create`, `frontier.enqueue_origin`. |
| I3 | Crawl **recursively** follows **http(s)** links found in **HTML** until no more **queued** work or depth would exceed *k*. | `extract_links_and_text`; children enqueued at `parent.depth + 1` only if `<= max_depth`. |
| I4 | **Duplicate URLs are not enqueued twice within the same run** (per normalized URL). | SQLite `UNIQUE (crawl_run_id, url)` on `frontier`; `url_known_for_run` + `try_enqueue_url`. |
| I5 | Each fetched URL produces a **page** row (URL after redirect normalization where applicable), **HTTP metadata**, optional **title** and **text** for search. | `Fetcher` + `extract_title` / `extract_links_and_text` or fallback text slice for non-HTML success. |
| I6 | After a successful fetch, the page is **indexed** (tokenized; term frequencies stored) so it can appear in search. | `Indexer.index_page` on `fetch_status == "ok"`. |
| I7 | User can **initialize** the database and **inspect** high-level state. | CLI: `init-db`, `status`. |

### 2.2 Search (`search`)

| ID | Requirement | Implementation notes |
|----|-------------|----------------------|
| S1 | User supplies a **query string**. | CLI: `python3 -m src.main search --query "..."`. |
| S2 | Results are **keyword-based** (token overlap with indexed content), not semantic/embedding search. | Shared tokenizer with indexer; `terms` / `page_terms`. |
| S3 | Each result is **`(relevant_url, origin_url, depth)`**. | `SearchEngine.search` returns this triple; `origin_url` is the run seed, `depth` from the stored page. |
| S4 | Results are **ranked** by a deterministic, documented score. | `src/indexer/ranking.py` (`score_page`). |
| S5 | Empty or unmatchable queries yield **no results** (no error to the user for normal input). | Blank query, no tokens after tokenization, or unknown terms → `[]`. |

---

## 3. Non-functional requirements

| Area | Requirement | As implemented |
|------|-------------|----------------|
| **Platform** | Runs on **localhost** with a **local** database file. | SQLite path from `config/default.json` (default `data/crawler.db`); `PRAGMA journal_mode = WAL`. |
| **Dependencies** | Prefer **standard library** for crawl, parse, HTTP, and DB. | Runtime uses stdlib; `requirements.txt` documents Python **3.11+**. |
| **Durability** | Crawl and index state survive process restarts **in principle** via SQLite. | All frontier/pages/terms persisted; see limitations for crash edge cases (`processing` / `indexing`). |
| **Incremental visibility** | Work is **committed per URL** so storage updates are visible without waiting for the full crawl. | `CrawlCoordinator` loop: `conn.commit()` after each claimed frontier entry. |
| **Backpressure** | Crawl must not grow an **unbounded** queued frontier in memory; load must be **bounded**. | Before each child enqueue: `wait_for_enqueue_slot` while `queued` count ≥ `queue_max_size` (config). |
| **Observability** | Operator can see DB location, counts, and recent crawl progress. | `status` command and crawl summary after `index`. |
| **Throughput model** | Predictable, simple concurrency story. | **Single-threaded** crawl loop (one URL at a time); see limitations. |

---

## 4. Assumptions

- **Localhost / single process**: one Python process, one SQLite file; **no** distributed crawl, **no** separate search cluster.
- **Educational use**: targets are small or permitted sites; operators are responsible for **not** abusing third-party servers.
- **HTML-centric**: link discovery uses **static HTML** parsing only (**no** JavaScript rendering).
- **Trust boundary**: the system does **not** implement **`robots.txt`** or a full politeness policy; that is an intentional **out-of-scope** tradeoff (see Architect scope and limitations below).
- **Configuration**: optional JSON config (`--config`); defaults include timeouts, `User-Agent`, `queue_max_size`, and a **`max_workers`** field **reserved for a future thread pool** — the current coordinator **does not** spawn multiple fetch workers.

---

## 5. Architecture overview

```
CLI (src/cli.py)
    → init-db / index / search / status
         │
         ├─ index ──► CrawlCoordinator (src/crawler/coordinator.py)
         │                 │
         │                 ├─ FrontierRepository (claim, enqueue, status)
         │                 ├─ fetch_page (src/crawler/fetcher.py)
         │                 ├─ extract_* (src/crawler/extractor.py)
         │                 ├─ normalize_url (src/crawler/normalizer.py)
         │                 ├─ PagesRepository (persist page rows)
         │                 └─ Indexer (src/indexer/indexer.py)
         │
         └─ search ──► SearchEngine (src/search/engine.py)
                           └─ SearchRepository + ranking (src/indexer/ranking.py)

Persistence: SQLite schema (src/storage/schema.sql), Repositories (src/storage/repositories.py)
```

**Modules (concise):**

- **Crawler**: coordinator loop, frontier lifecycle, fetch, extract, normalize, enqueue with depth and deduplication rules.
- **Storage**: SQLite tables for runs, frontier, pages, global `terms`, and `page_terms` postings.
- **Indexer**: tokenizer, `indexed_status` transitions, replace postings per page.
- **Search**: query tokenization, term id resolution, candidate aggregation from **`indexed`** pages only, scoring, sort, truncate.

---

## 6. Indexing flow (end-to-end)

1. **CLI** `index` opens config, builds `CrawlCoordinator`, calls `run(origin, max_depth)`.
2. **Open DB** with schema; **create** `crawl_runs` row (`active`); **insert** frontier row for normalized origin at depth `0` (`queued`).
3. **Loop** until no `queued` rows:
   - **Claim** next row: transition **`queued` → `processing`** (implementation in `FrontierRepository.claim_next_queued`).
   - If `entry.depth > max_depth`, mark frontier **`failed`** and continue.
   - **Fetch** URL (timeout, redirects, content-type/body rules in `fetcher.py`).
   - Derive **page URL** (normalize `final_url` on success when valid).
   - **Parse** title and, for crawlable HTML, links + visible text; otherwise limited raw text for non-HTML success.
   - **Upsert page** (`pages.save_fetched_page`) with `indexed_status = not_indexed` initially.
   - If fetch OK: **`Indexer.index_page`**: set `indexing` → write `terms` / `page_terms` → set `indexed` (or `index_failed` on error).
   - If fetch OK and HTML: for each normalized child link, **wait for enqueue slot** (backpressure), skip if URL already known for run, else **enqueue** at `depth + 1` if `<= max_depth`.
   - Set frontier row **`done`** or **`failed`**; **commit** transaction for this URL.
4. Mark crawl run **`completed`**; return **run id** and **progress snapshot** (frontier counts, pages recorded, max depth seen).

---

## 7. Search flow

1. **CLI** `search` loads config, opens DB, constructs `SearchEngine` with `SearchRepository`.
2. **Normalize input**: empty/whitespace → no results.
3. **Tokenize** query with the same pipeline as indexing (`src/indexer/tokenizer.py`). No tokens (e.g. only stopwords) → no results.
4. **Resolve** query tokens to `terms.id` list; if none exist in DB → no results.
5. **Load candidates**: SQL aggregates per **indexed** page — matched distinct query terms, sums of body and title frequencies (`indexed_candidate_stats_for_term_ids`). Default **`LIMIT 2000`** candidates before ranking.
6. **Score** each row with `score_page(...)` in **`src/indexer/ranking.py`**.
7. **Sort** by score descending, then URL; return top **`50`** as `(url, origin_url, depth)`.

---

## 8. Backpressure strategy

- **Mechanism**: Before enqueueing a newly discovered URL, the coordinator calls **`wait_for_enqueue_slot`** (`src/crawler/frontier.py`).
- **Condition**: Block (poll sleep) while the count of frontier rows in status **`queued`** for the current run is **≥ `queue_max_size`** from configuration (`config/default.json`).
- **Effect**: Producers (link extraction) **pause** when the **persisted** queue is full, keeping work **bounded** without an unbounded in-memory frontier.
- **Consumer model**: A **single sequential worker** drains the queue (one claim/process/commit cycle at a time). This matches SQLite’s practical single-writer pattern and simplifies correctness.

---

## 9. Persistence model

| Entity | Role |
|--------|------|
| **`crawl_runs`** | One row per `index` invocation: `origin_url`, `max_depth`, `status` (`active` / `completed` / `failed`), timestamps. |
| **`frontier`** | Discovered URLs per run: `url`, `origin_url`, `depth`, `discovered_from`, `status` (`queued` / `processing` / `done` / `failed`). **Unique** `(crawl_run_id, url)`. |
| **`pages`** | Stored document per run and URL: content, fetch metadata, **`indexed_status`** (`not_indexed` / `indexing` / `indexed` / `index_failed`). **Unique** `(crawl_run_id, url)`. |
| **`terms`** | Global vocabulary: `term` string **unique**. |
| **`page_terms`** | Postings: `(page_id, term_id)` with **`frequency`** (body) and **`in_title_frequency`**. |

**Connection behavior** (`src/storage/db.py`): WAL mode, foreign keys on, `busy_timeout`; callers commit explicitly so each crawled URL’s page + index updates can be read by a concurrent **search** process (separate CLI invocation).

---

## 10. Search consistency model

- **Visibility rule**: Search queries include only rows with **`pages.indexed_status = 'indexed'`**.
- **During an active crawl** (theoretically: second terminal + second process): new pages appear in search **after** their URL’s transaction commits and the indexer reaches **`indexed`**. Pages in **`indexing`** are **not** returned — avoids exposing partial postings (see docstring in `src/indexer/indexer.py`).
- **Model name**: **Eventual consistency** — the result set **grows and improves** as more pages finish indexing; there is no guarantee that every discovered-but-not-yet-indexed page appears immediately.
- **Cross-run search**: The implementation searches **all** indexed pages in the database (not restricted to a single `crawl_run_id`), unless filtered elsewhere in the future.

---

## 11. Limitations (honest scope)

Aligned with the code and README-level caveats:

- **Single-threaded crawl** — no parallel fetch pool; `max_workers` in config is **not** used for concurrency today.
- **No `robots.txt`** or crawl-delay policy.
- **URL normalization is limited** — scheme/host/path variants and **redirect final URLs** can create **extra rows** or near-duplicates compared to human “one canonical URL.”
- **No `<base href>`** handling; relative links resolve against the **response URL** passed to the extractor only.
- **Resume / crash recovery** is partial: `requeue_stale_processing` exists in storage but **no CLI** exposes it; stuck **`processing`** or **`indexing`** rows may need manual intervention or a fresh run.
- **Fetcher body size cap** and **non-HTML** handling imply incomplete text for some resources.
- **Search cap**: candidate SQL **`LIMIT`** (default 2000) and result **`LIMIT`** (50) mean very large corpora may miss some matches in ranking.
- **Tokenizer / stopwords** — queries that tokenize to nothing yield empty results.

---

## 12. Traceability

| Topic | Primary code |
|-------|----------------|
| Crawl loop | `src/crawler/coordinator.py` |
| Backpressure | `src/crawler/frontier.py` (`wait_for_enqueue_slot`) |
| Fetch / redirect | `src/crawler/fetcher.py` |
| Indexing / status | `src/indexer/indexer.py` |
| Ranking | `src/indexer/ranking.py` |
| Search | `src/search/engine.py` |
| Schema | `src/storage/schema.sql` |

---

*End of PRD.*
