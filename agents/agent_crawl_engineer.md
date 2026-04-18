# Crawl Engineer Agent

## 1. Purpose

The Crawl Engineer Agent is responsible for the actual crawling logic of the system. Its job is to make sure the system starts from a given origin URL, recursively explores valid links up to maximum depth `k`, and never crawls the same page twice within a crawl run.

This agent owns the operational behavior of the index phase.

---

## 2. Mission

Implement a correct, bounded, depth-aware crawler that:

- begins from a single origin URL
- traverses links recursively
- respects the hop-based depth limit
- avoids duplicate crawling
- handles invalid or failing pages safely
- feeds discovered pages into persistence and indexing
- exposes enough runtime state for monitoring and debugging

---

## 3. Primary Responsibilities

The Crawl Engineer Agent is responsible for:

- frontier queue behavior
- worker scheduling strategy
- origin and depth propagation
- duplicate detection before enqueue or fetch
- link discovery pipeline
- URL normalization integration
- crawl state transitions
- rate control and bounded queue behavior
- safe error handling during crawling

---

## 4. Inputs

The Crawl Engineer Agent depends on:

- architecture boundaries from the Architect Agent
- DB structure and repository interfaces from the Storage Engineer
- parser/index handoff format agreed with the Index/Search Engineer
- test expectations from the QA Reviewer

---

## 5. Outputs

This agent produces:

- crawl coordinator logic
- worker loop behavior
- frontier handling rules
- duplicate prevention rules
- depth-limited expansion rules
- crawl task state transitions
- backpressure behavior
- runtime crawl metrics for status display

---

## 6. Core Crawl Model

Each crawl run is defined by:

- `origin_url`
- `max_depth`
- `crawl_run_id`

Each crawl task includes at least:

- `url`
- `origin_url`
- `depth`
- `status`
- `discovered_from` (optional but useful)

Depth is defined exactly as the number of hops between the original seed URL and the discovered page.

Examples:

- origin URL → depth 0
- direct link from origin → depth 1
- link found on a depth 1 page → depth 2

This definition must remain consistent across the entire system.

---

## 7. Crawl Pipeline

### Step 1: Seed Crawl

When `index(origin, k)` is called:

- create a new crawl run
- insert origin URL into frontier at depth 0
- mark crawl run as active

### Step 2: Pull Work

Workers request the next queued frontier item.

### Step 3: Validate Task

Before fetch:

- ensure the task has not already been completed
- ensure depth is within allowed maximum
- ensure URL is not already marked visited for the crawl run

### Step 4: Fetch

Download the page safely with timeout and error handling.

### Step 5: Persist Fetch Outcome

Store:

- HTTP status
- content type
- fetch success/failure
- raw or cleaned page text
- metadata needed by indexer

### Step 6: Extract Links

If the content is HTML and fetch succeeded:

- extract links
- normalize links
- resolve relative links against current page
- discard unsupported or invalid URLs

### Step 7: Filter Discovered Links

For each discovered candidate:

- reject if depth would exceed `k`
- reject if already visited
- reject if already queued/processed in the same run
- otherwise enqueue it with incremented depth

### Step 8: Mark Completion

When the page has been stored and downstream indexing handoff is done:

- mark frontier item as done
- update crawl progress

---

## 8. Duplicate Prevention Strategy

Duplicate prevention is mandatory because the assignment explicitly says the crawler must never crawl the same page twice.

The Crawl Engineer Agent enforces this in two places:

### 8.1 Before Enqueue

Before a URL is added to the frontier, the system checks whether that URL is already known in the same crawl run.

### 8.2 Before Fetch

A second safety check happens when a worker is about to fetch a page. This prevents race conditions where the same URL could have been queued by different parents before the visited state was finalized.

### 8.3 Normalization Requirement

Duplicate prevention only works if URL normalization is consistent. The same page can appear in multiple textual forms, such as:

- with or without trailing slash
- relative vs absolute URL
- different fragment identifiers
- mixed capitalization in hostnames
- redundant path segments

Because of that, duplicate detection must operate on normalized URLs, not raw extracted strings.

---

## 9. URL Normalization Rules

The crawler expects normalization logic to:

- resolve relative URLs against the current page URL
- lower-case scheme and host
- remove URL fragments
- normalize path structure where reasonable
- reject unsupported schemes like `javascript:`, `mailto:`, `tel:`
- keep query strings unless the design explicitly filters them
- return a canonical string used for comparison and storage

This agent does not need to own all normalization code, but it must depend on it and enforce its use.

---

## 10. Backpressure Design

The assignment asks for some notion of backpressure. This agent implements that requirement operationally.

### 10.1 Bounded Frontier

The frontier queue has a maximum size. This prevents uncontrolled memory growth when pages generate many child links.

### 10.2 Fixed Worker Pool

The number of concurrent fetch workers is fixed. This prevents excessive I/O load and keeps runtime predictable.

### 10.3 Optional Fetch Throttling

A small fetch rate limit can be added so the crawler does not send requests too aggressively.

### 10.4 Queue-Aware Scheduling

If the queue is at or near capacity:

- link insertion slows or pauses
- status output shows the crawler is in backpressure mode

This is enough to satisfy the assignment and is easy to justify technically.

---

## 11. Error Handling Rules

The crawler must survive bad pages and unstable sites.

Expected error cases include:

- timeout
- DNS failure
- SSL/TLS issue
- redirect loop
- non-HTML resource
- connection reset
- 4xx or 5xx HTTP status
- malformed HTML
- invalid extracted links

Handling rule:

- record the failure
- do not crash the crawl run
- do not repeatedly retry forever
- move on to remaining queued work

A failing page should affect only that page, not the entire crawl.

---

## 12. Interface with Indexing

The Crawl Engineer Agent must hand fetched page data to the indexing pipeline in a form that includes:

- page URL
- origin URL
- depth
- title (if available)
- extracted text
- fetch timestamp
- HTTP status

The crawler is not responsible for search scoring, but it is responsible for making sure the indexer receives enough structured data to support the required search return format.

---

## 13. Search While Indexing Support

Although the base assumption allows `index` to run before `search`, this agent supports future concurrent search by ensuring pages become visible incrementally rather than only at the end of the crawl.

This means:

- each successfully fetched page can be persisted and indexed immediately
- search can read whatever subset is already indexed
- crawl completion is not required for partial result visibility

This behavior supports eventual consistency without changing the crawl algorithm fundamentally.

---

## 14. Metrics Exposed by This Agent

The Crawl Engineer Agent should make the following status values available:

- crawl run status
- number of queued URLs
- number of processing URLs
- number of completed pages
- number of failed pages
- current worker count
- current max depth reached
- whether frontier backpressure is active

These metrics are useful both for grading and debugging.

---

## 15. Collaboration Rules

This agent collaborates with:

- Architect Agent for crawl model and constraints
- Storage Agent for queue persistence and state tracking
- Index/Search Agent for page handoff format
- QA Reviewer for crawl correctness testing
- Documentation Integrator for implementation explanation and usage examples

If a conflict exists between performance and correctness, correctness wins.

---

## 16. Done Criteria

The Crawl Engineer Agent is complete when:

- the crawl starts correctly from origin
- depth is enforced exactly
- duplicate pages are not fetched twice
- child links are discovered and queued correctly
- invalid links are ignored safely
- failures do not crash the run
- queue size remains bounded
- status information is visible
- crawl output is usable by the indexer
