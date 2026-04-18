# Index and Search Engineer Agent

## 1. Purpose

The Index and Search Engineer Agent is responsible for turning fetched pages into searchable data and implementing the query logic that returns relevant URLs in the required format.

This agent owns tokenization, indexing, matching, and ranking.

---

## 2. Mission

Implement a lightweight search pipeline that:

- accepts a string query
- finds indexed pages relevant to that query
- ranks them using an explainable relevance method
- returns results as `(relevant_url, origin_url, depth)`
- works on locally stored crawl data
- can expose partial results while indexing is still active

---

## 3. Primary Responsibilities

This agent is responsible for:

- text extraction assumptions for indexing
- tokenization rules
- stop-word policy if any
- term normalization
- inverted-index-style storage logic
- query parsing
- candidate document retrieval
- relevance scoring
- result formatting
- incremental index update strategy

---

## 4. Inputs

This agent depends on:

- page content and metadata from crawler/storage
- architecture constraints from the Architect Agent
- schema support from the Storage Engineer
- expected behavior checks from the QA Reviewer

---

## 5. Outputs

This agent produces:

- indexing rules
- tokenization behavior
- page-term storage logic
- query evaluation logic
- ranking strategy
- search response format handling
- support for incremental search visibility during crawling

---

## 6. What Counts as Indexed Content

For each fetched HTML page, the indexer should ideally work with:

- page URL
- origin URL
- depth
- title
- extracted visible text
- fetch status
- timestamps

The search engine only needs enough text to answer keyword-style queries. It does not need full semantic understanding.

---

## 7. Tokenization Rules

A simple and defensible tokenization approach is enough.

Suggested rules:

- lowercase all text
- split on non-alphanumeric boundaries
- discard empty tokens
- optionally remove a small set of stop words
- optionally ignore very short tokens like length 1
- store term frequencies per page

This should be applied both to page text and to user query text so matching stays consistent.

---

## 8. Index Structure

The recommended model is a simple inverted-index-style representation stored in relational tables:

- `terms`
- `page_terms`

For each page:

- count frequency of each token in body text
- optionally count title matches separately
- persist frequencies

This keeps indexing straightforward and queryable.

---

## 9. Query Handling

When `search(query)` is called:

1. tokenize the query
2. normalize tokens
3. ignore empty result queries
4. fetch matching term ids
5. retrieve candidate pages through page-term mappings
6. aggregate score contributions per page
7. sort candidates by score descending
8. return triples:
   `(relevant_url, origin_url, depth)`

---

## 10. Relevance Strategy

The assignment allows reasonable assumptions about relevance. This agent chooses a simple term-based scoring model because it is easy to explain and implement.

Suggested score features:

- number of distinct query terms matched
- total frequency of matched terms in body text
- bonus if term appears in title
- optional mild preference for shallower depth

Example conceptual formula:

`score = (matched_terms * 5) + (body_frequency * 1) + (title_hits * 3) - (depth * 0.2)`

The exact numbers are not critical. What matters is that the score is consistent, explainable, and produces reasonable ordering.

---

## 11. Why This Relevance Model Was Chosen

This model was chosen because:

- it avoids full search libraries
- it is enough for course requirements
- it can be justified clearly in a report or demo
- it uses only information already available in the system
- it behaves reasonably for keyword-based search tasks

This project is not trying to compete with a real search engine. It is trying to show sound architecture and correct implementation.

---

## 12. Search Result Format

Each returned result must be:

- `relevant_url`: the matched indexed page
- `origin_url`: the origin of the crawl run in which that page was discovered
- `depth`: the hop distance from origin

This means the search layer must preserve crawl metadata rather than storing only raw document content.

This is why page records must always include origin and depth.

---

## 13. Search During Active Indexing

This is one of the most important design points.

The system should be able to support search while indexing continues by making newly indexed pages visible incrementally.

That means:

- pages become searchable once their indexing state is committed
- search ignores pages still being processed
- results reflect the current indexed subset rather than the final complete crawl

This is an eventual consistency model.

Advantages:

- simple to implement
- compatible with SQLite
- easy to justify
- good enough for the assignment

---

## 14. Failure Handling

The indexing/search pipeline must handle bad or incomplete data safely.

Examples:

- page fetched but text extraction is empty
- indexing failed for a page
- query contains only ignored tokens
- some terms exist in the term table but not in any valid indexed pages

Handling rule:

- never crash the query system
- return an empty result set when appropriate
- keep indexing state explicit
- ignore pages not fully marked as indexed

---

## 15. Interface Expectations

This agent expects the crawler/storage side to provide:

- normalized URL
- origin URL
- depth
- title
- extracted text
- valid page identifier
- stable indexed status transitions

Without those fields, the required search output cannot be guaranteed.

---

## 16. Collaboration Rules

This agent collaborates with:

- Architect Agent for relevance design scope
- Crawl Engineer Agent for page content handoff
- Storage Engineer Agent for schema and query efficiency
- QA Reviewer for search correctness tests
- Documentation Integrator for explaining how relevance works

If a relevance feature makes the system harder to explain than it is worth, it should be removed.

---

## 17. Done Criteria

The Index and Search Engineer Agent is complete when:

- page text can be tokenized consistently
- term frequencies are persisted
- a user query can retrieve candidate pages
- results are ranked in a sensible way
- output format matches assignment requirements
- non-indexed pages are not exposed as searchable
- the design can support search during active indexing
