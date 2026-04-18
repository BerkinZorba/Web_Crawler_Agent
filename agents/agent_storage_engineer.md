# Storage Engineer Agent

## 1. Purpose

The Storage Engineer Agent is responsible for all persistent state in the system. Its job is to ensure that the crawler, indexer, and search components can rely on a stable local database for storing crawl progress, page data, discovered URLs, and searchable term information.

This agent owns the database model and persistence behavior.

---

## 2. Mission

Design and implement a local persistence layer that supports:

- crawl run creation and tracking
- durable frontier storage
- duplicate prevention
- page metadata storage
- incremental indexing
- efficient query lookup
- optional resume support after interruption

The persistence model must be simple enough to run locally but structured enough to support clean system behavior.

---

## 3. Primary Responsibilities

The Storage Engineer Agent is responsible for:

- selecting the local database strategy
- designing the schema
- defining primary keys and unique constraints
- modeling crawl state transitions
- supporting duplicate detection through persistence
- storing page and term data
- enabling search queries over indexed documents
- providing repository/helper methods for other modules
- ensuring writes are durable and reads are practical

---

## 4. Inputs

This agent depends on:

- architecture and entity expectations from the Architect Agent
- crawl lifecycle needs from the Crawl Engineer Agent
- indexing and retrieval needs from the Index/Search Engineer Agent
- validation requirements from the QA Reviewer

---

## 5. Outputs

This agent produces:

- database selection rationale
- schema definitions
- repository layer or SQL helpers
- persistence contracts for crawler and search modules
- state transition rules for crawl records
- resume strategy
- consistency notes for concurrent indexing/search

---

## 6. Database Choice

SQLite is selected as the database.

### Why SQLite

- works locally with no external setup
- easy to include in a student project
- strong fit for localhost execution
- supports transactions and indexes
- enough for moderate concurrent read/write if used carefully
- easy to explain to instructors

### Limitations Acknowledged

- not meant for large distributed crawling
- single-writer characteristics can become a bottleneck
- not a long-term production solution for large search systems

Those limitations are acceptable for this assignment.

---

## 7. Data Entities

The Storage Engineer Agent models the following main entities:

### 7.1 Crawl Runs

Represents one invocation of `index(origin, k)`.

Stores:

- crawl run id
- origin URL
- max depth
- lifecycle status
- timestamps

### 7.2 Frontier Entries

Represents URLs discovered for possible crawling.

Stores:

- crawl run id
- URL
- origin URL
- depth
- status
- discovered_from
- timestamps

### 7.3 Visited / Known URL State

Supports duplicate prevention. This may be implemented as:

- a dedicated visited table
- a unique constraint on frontier URLs per run
- or a hybrid model

The key point is that a normalized URL must not be processed twice in the same run.

### 7.4 Pages

Represents fetched page content and metadata.

Stores:

- crawl run id
- normalized URL
- origin URL
- depth
- title
- extracted text
- HTTP status
- fetch time
- indexing status

### 7.5 Terms

Stores canonical token entries.

### 7.6 Page-Term Mappings

Stores frequency relationships between pages and indexed terms.

This table makes keyword search possible.

---

## 8. Suggested Schema

### 8.1 `crawl_runs`

Fields:

- `id`
- `origin_url`
- `max_depth`
- `status`
- `created_at`
- `updated_at`

### 8.2 `frontier`

Fields:

- `id`
- `crawl_run_id`
- `url`
- `origin_url`
- `depth`
- `discovered_from`
- `status`
- `created_at`
- `updated_at`

Recommended statuses:

- `queued`
- `processing`
- `done`
- `failed`

Recommended uniqueness:

- unique `(crawl_run_id, url)`

### 8.3 `pages`

Fields:

- `id`
- `crawl_run_id`
- `url`
- `origin_url`
- `depth`
- `title`
- `content_text`
- `http_status`
- `fetch_status`
- `indexed_status`
- `fetched_at`

### 8.4 `terms`

Fields:

- `id`
- `term`

Unique:

- `term`

### 8.5 `page_terms`

Fields:

- `page_id`
- `term_id`
- `frequency`
- `in_title_frequency` or a simple title-hit indicator

Primary key:

- `(page_id, term_id)`

---

## 9. Persistence Rules

### 9.1 Frontier Insertion Rule

A discovered URL is only inserted if:

- it passes normalization
- it does not exceed max depth
- it is not already known for that crawl run

### 9.2 Processing Claim Rule

When a worker takes a frontier task:

- the corresponding row is moved from `queued` to `processing`

This prevents repeated processing and improves traceability.

### 9.3 Completion Rule

When a page is processed fully:

- frontier status is updated to `done`
- page row is stored or updated
- indexing state is recorded

### 9.4 Failure Rule

If crawling fails:

- frontier row is updated to `failed`
- page or error metadata may still be recorded
- no unbounded retry loop is allowed

---

## 10. Duplicate Prevention Through Storage

Storage is one of the main defenses against duplicate crawling.

The system prevents duplicates by making normalized URL identity persistent. That means even if the process discovers the same link from multiple parent pages, the database acts as the source of truth and rejects duplicate entries.

This is important because in concurrent crawls, in-memory duplicate checks alone are not enough.

Recommended rule:

- enforce uniqueness at the database level
- still keep in-memory checks for speed
- treat the DB constraint as the final safeguard

---

## 11. Resume Support

Resume support is optional in the assignment, but it is worth implementing if possible.

The Storage Engineer Agent supports resumability by storing enough crawl state to reconstruct unfinished work:

- crawl run status
- frontier items still queued
- frontier items in processing
- completed pages
- failed items

If the program stops unexpectedly, a resume command could:

- find active or interrupted runs
- reset `processing` items back to `queued` if needed
- continue from the saved frontier state

This is a practical and credible enhancement.

---

## 12. Search While Indexing Support

To support search during active indexing, persistence must allow committed partial visibility.

This means:

- pages can be inserted as soon as they are fetched
- terms can be inserted as soon as a page is tokenized
- `indexed_status` distinguishes searchable pages from non-searchable ones

Suggested statuses:

- `not_indexed`
- `indexing`
- `indexed`
- `index_failed`

Search queries should only consider pages with `indexed_status = indexed`.

This keeps search results consistent even while the crawler is still active.

---

## 13. Performance Considerations

The Storage Engineer Agent does not chase extreme optimization, but it does apply basic sensible measures:

- create indexes on:
  - frontier status
  - crawl_run_id
  - page URL
  - term value
  - page-term relationships
- use transactions for grouped writes
- avoid unnecessary repeated lookups
- enable WAL mode for better concurrent read/write behavior
- keep write transactions short

That is enough for localhost scale.

---

## 14. Collaboration Rules

This agent collaborates with:

- Architect Agent to align schema with required flows
- Crawl Engineer Agent to support queue/state management
- Index/Search Engineer Agent to support token storage and query retrieval
- QA Reviewer to validate constraints and state correctness
- Documentation Integrator to explain schema and persistence rationale

If a proposed data model is difficult to explain or test, it should be simplified.

---

## 15. Done Criteria

The Storage Engineer Agent is complete when:

- crawl runs can be created and tracked
- frontier state is persisted
- duplicate URLs are blocked reliably
- fetched pages are stored correctly
- search-relevant term data is persisted
- partial indexed state is queryable
- local restart/resume is possible or at least well-supported by stored state
- schema is documented and justified
